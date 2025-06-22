/* eslint-disable no-console */
const fetch = require('node-fetch'); // ou 'axios' se preferir
const AbortController = require('abort-controller'); // Para Node < 15

/************************************************************
 * CONFIGURAÇÕES
 ************************************************************/
const CONFIG = {
  targetHost: 'https://seu-alvo-aqui.com', // REQUIRED: Replace with your authorized target
  basePaths: [                            // REQUIRED: Paths to test on the targetHost
    '/swagger-ui.html',
    '/v2/api-docs',
    '/swagger.json',
    '/openapi.json',
    '/api-docs',
    '/docs',
    '/',
    // Adicione outros paths relevantes, e.g., '/admin', '/login', '/api/v1/users'
  ],
  httpMethods: ['GET'], // Methods to test for each URL variation

  // Optional configurations:
  timeoutMs: 15000,               // Timeout for each request in milliseconds
  requestDelayMs: 200,            // Delay between test requests in milliseconds (to be polite)
  verboseLevel: 1,                // Logging verbosity: 0 (quiet), 1 (normal), 2 (detailed/debug)

  extraHeaders: {
    // Example: 'User-Agent': 'BugBountyScanner/1.0',
    // Example: 'Authorization': 'Bearer yourtoken', // If needed for some paths
  },

  // Response handling
  snippetContentTypes: [          // Content types for which to grab a body snippet
    'text/html',
    'text/plain',
    'application/json',
    'application/xml',
    'text/xml',
    'application/javascript'
  ],
  snippetLength: 500,             // Max length of the response body snippet

  // WAF/Bypass detection tuning
  wafBlockStatusCodes: [          // HTTP status codes initially considered as a WAF block
    403, // Forbidden
    406, // Not Acceptable
    412, // Precondition Failed
    429, // Too Many Requests (can sometimes be a WAF/rate limiter)
    // Common custom codes (consult target WAF documentation if known)
    // 478, (Example, F5 uses this sometimes)
  ],
};

/************************************************************
 * FUNÇÕES AUXILIARES
 ************************************************************/

/**
 * Processa segmentos de path para testes de bypass, preservando codificações existentes.
 * (Atualmente não utilizada no script principal, mas mantida para referência ou uso futuro)
 * @param {string} pathSegment
 * @returns {string}
 */
function processPathSegmentForTest(pathSegment) {
  let result = '';
  for (let i = 0; i < pathSegment.length; i++) {
    const char = pathSegment[i];
    if (
      char === '%' &&
      i + 2 < pathSegment.length &&
      /[0-9a-fA-F]{2}/.test(pathSegment.substring(i + 1, i + 3))
    ) {
      result += pathSegment.substring(i, i + 3);
      i += 2;
    } else if ('/.:;=?&#'.includes(char)) {
      result += char;
    } else {
      result += encodeURIComponent(char);
    }
  }
  return result;
}

/**
 * Testa uma URL com uma técnica específica e registra os resultados.
 * @param {string} urlToTest - A URL completa a ser testada.
 * @param {string} techniqueName - Nome da técnica de bypass.
 * @param {number|null} originalStatusCode - Status code da requisição original (baseline).
 * @param {string} method - Método HTTP a ser utilizado.
 * @returns {Promise<object|null>} Um objeto de achado se algo notável for detectado, senão null.
 */
async function testUrl(urlToTest, techniqueName, originalStatusCode, method = 'GET') {
  if (CONFIG.verboseLevel >= 1) {
    console.log(`\n[+] Técnica: ${techniqueName}`);
    console.log(`    -> URL: ${method} ${urlToTest}`);
  } else if (CONFIG.verboseLevel === 0) {
    // Em modo quieto, só logaremos em caso de erro crítico ou sucesso de bypass.
    // A main function se encarrega de logar os achados.
  }


  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.timeoutMs);

    const response = await fetch(urlToTest, {
      method,
      headers: { ...CONFIG.extraHeaders },
      signal: controller.signal,
      redirect: 'manual', // importante para ver 30x em vez de segui-los automaticamente
    });

    clearTimeout(timeoutId);

    const status = response.status;
    const responseHeaders = Object.fromEntries(response.headers.entries());
    let responseBodySnippet = '';

    const contentType = response.headers.get('content-type') || '';
    if (CONFIG.snippetContentTypes.some(ct => contentType.toLowerCase().includes(ct.toLowerCase()))) {
      const text = await response.text();
      responseBodySnippet = text.substring(0, CONFIG.snippetLength) + (text.length > CONFIG.snippetLength ? '...' : '');
    }

    if (CONFIG.verboseLevel >= 1) {
      console.log(`    -> Resposta: HTTP ${status}`);
    }

    const isOriginalBlocked = originalStatusCode && CONFIG.wafBlockStatusCodes.includes(originalStatusCode);
    const isCurrentBlocked = CONFIG.wafBlockStatusCodes.includes(status);

    let finding = null;

    if (isOriginalBlocked && !isCurrentBlocked && status !== originalStatusCode) {
      const message = `    -> POSSÍVEL BYPASS: Original ${originalStatusCode}, Atual ${status}.`;
      if (CONFIG.verboseLevel >= 0) console.log(message); // Loga bypasses mesmo em modo quieto
      finding = { type: 'BYPASS', techniqueName, url: urlToTest, method, originalStatusCode, currentStatus: status, headers: responseHeaders, bodySnippet: responseBodySnippet };
    } else if (status === 200 && originalStatusCode !== 200) {
      const message = `    -> SUCESSO (200). Recurso acessível (Original ${originalStatusCode}).`;
      if (CONFIG.verboseLevel >= 1) {
        console.log(message);
        console.log('    -> Cabeçalhos:', responseHeaders);
        if (responseBodySnippet) console.log('    -> Corpo (snippet):\n', responseBodySnippet);
      } else if (CONFIG.verboseLevel === 0) {
         console.log(`[+] ${message} URL: ${method} ${urlToTest}`);
      }
      finding = { type: 'SUCCESS_200_UNEXPECTED', techniqueName, url: urlToTest, method, originalStatusCode, currentStatus: status, headers: responseHeaders, bodySnippet: responseBodySnippet };
    } else if (status === 200 && originalStatusCode === 200) {
        if (CONFIG.verboseLevel >= 2) { // Loga 200s que continuam 200 apenas em verbose máximo
            console.log('    -> SUCESSO (200). Recurso continua acessível.');
            console.log('    -> Cabeçalhos:', responseHeaders);
            if (responseBodySnippet) console.log('    -> Corpo (snippet):\n', responseBodySnippet);
        }
        // Não consideramos um "finding" para o sumário se era 200 e continua 200 com a mesma URL (baseline)
        // ou se a técnica não alterou significativamente a URL e o status permaneceu 200.
    } else if (status === 400 && (responseHeaders.server || '').toLowerCase().includes('nginx')) {
      const message = '    -> RESPOSTA 400 do Nginx. Possível bypass parcial ou má formação causada pela técnica.';
      if (CONFIG.verboseLevel >= 1) console.log(message);
      finding = { type: 'NGINX_400', techniqueName, url: urlToTest, method, originalStatusCode, currentStatus: status, headers: responseHeaders, bodySnippet: responseBodySnippet };
    } else {
      if (CONFIG.verboseLevel >= 1) {
        console.log(`    -> Status ${status} (Original: ${originalStatusCode}).`);
        if (CONFIG.verboseLevel >= 2) { // Log headers/body para outros casos apenas em debug
            console.log('    -> Cabeçalhos:', responseHeaders);
            if (responseBodySnippet) console.log('    -> Corpo (snippet):\n', responseBodySnippet);
        }
      }
    }
    if (CONFIG.verboseLevel >= 1) console.log('---------------------------------------------------');
    return finding;

  } catch (error) {
    if (CONFIG.verboseLevel >= 0) { // Loga erros mesmo em modo quieto
        if (error.name === 'AbortError') {
        console.log(`    -> Timeout excedido para ${method} ${urlToTest}.`);
        } else if (error.code === 'ENOTFOUND') {
        console.log(`    -> Host não resolvido (DNS) para ${method} ${urlToTest}.`);
        } else if (error.code === 'ECONNREFUSED') {
        console.log(`    -> Conexão recusada para ${method} ${urlToTest}.`);
        } else {
        console.error(`    -> Erro inesperado para ${method} ${urlToTest}: ${error.message}`);
        if (error.type && CONFIG.verboseLevel >=1) console.error(`    -> Tipo de erro: ${error.type}`);
        }
        if (CONFIG.verboseLevel >= 1) console.log('---------------------------------------------------');
    }
    return null; // Erros não são "findings" para o sumário de bypass, mas são logados.
  }
}

/************************************************************
 * TÉCNICAS DE BYPASS
 ************************************************************/
// Comentário explicando a estrutura esperada:
// Array de funções, cada uma representando uma categoria de técnicas de bypass.
// Cada função recebe `basePath` (string) e deve retornar um array de objetos,
// onde cada objeto tem a forma: { url: string (path + query), name: string (nome da técnica) }.
// A `url` retornada é o segmento de path/query a ser anexado ao `CONFIG.targetHost`.
const bypassTechniques = [
  // Null Byte
  (basePath) => [
    { url: basePath + '%00', name: 'null_byte_suffix' },
    { url: basePath + '%00%00', name: 'double_null_byte_suffix' },
    { url: basePath.replace(/([?=&\/])/, '%00$1'), name: 'null_byte_before_special_char'}
  ],

  // Path Traversal like
  (basePath) => [
    { url: basePath + '/..%00/', name: 'path_traversal_null_suffix' },
    { url: basePath + '/...%00/', name: 'triplo_dot_null_suffix' },
    { url: basePath + '/../', name: 'path_traversal_simple' },
    { url: basePath + '/./', name: 'path_self_reference_suffix' },
  ],

  // Caracteres de controle
  (basePath) => [
    { url: basePath + '%0a', name: 'newline_suffix_lf' },
    { url: basePath + '%0d', name: 'carriage_return_suffix_cr' },
    { url: basePath + '%0d%0a', name: 'crlf_suffix' },
    { url: basePath + '%09', name: 'tab_char_suffix' }, // Added from plan
  ],

  // Double Encoding (full path)
  (basePath) => [
    { url: encodeURIComponent(encodeURIComponent(basePath)), name: 'double_encoded_full_path' },
  ],

  // Specific Character Encoding / Double Encoding
  (basePath) => [
    { url: basePath.replace(/\//g, '%252F'), name: 'double_encoded_slashes' },
    { url: basePath.replace(/\./g, '%2E'), name: 'encoded_dots_single' }, // . -> %2E (single)
    { url: basePath.replace(/\./g, '%252E'), name: 'double_encoded_dots' }, // . -> %2E -> %252E (double)
  ],

  // Unicode Encoding (non-standard %u)
  (basePath) => [
    { url: basePath.replace(/\//g, '%u002F'), name: 'unicode_slash_u002f' },
    { url: basePath.replace(/\./g, '%u002E'), name: 'unicode_dot_u002e' },
  ],

  // Random Mixed Case
  (basePath) => [{
    url: basePath.split('').map(char => Math.random() < 0.5 ? char.toUpperCase() : char.toLowerCase()).join(''),
    name: 'random_mixed_case'
  }],

  // Path Segment Manipulations
  (basePath) => {
    const variations = [];
    const parts = basePath.split('?');
    const pathOnly = parts[0];
    const query = parts.length > 1 ? `?${parts.slice(1).join('?')}` : '';
    let newPathTransformed; // Use a different variable name to avoid confusion with 'newPath' in outer scope if any

    // Insert /./
    if (pathOnly === '/') {
        newPathTransformed = '/./';
    } else if (pathOnly.endsWith('/')) {
        newPathTransformed = pathOnly + './';
    } else {
        const lastSlash = pathOnly.lastIndexOf('/');
        if (lastSlash === -1) {
            newPathTransformed = './' + pathOnly;
        } else if (lastSlash === 0) {
            newPathTransformed = '/./' + pathOnly.substring(1);
        } else {
            newPathTransformed = pathOnly.substring(0, lastSlash) + '/./' + pathOnly.substring(lastSlash + 1);
        }
    }
    if (newPathTransformed + query !== basePath) {
      variations.push({ url: newPathTransformed + query, name: 'path_insert_dot_slash_segment' });
    }

    // Replace last / with //
    let newPathForDoubleSlash = pathOnly; // Initialize with original pathOnly
    if (pathOnly !== '/' && !pathOnly.endsWith('//')) {
        const lastSlashIdx = pathOnly.lastIndexOf('/');
        if (lastSlashIdx === -1) {
            // Skip for "file.html"
        } else if (lastSlashIdx === 0 && pathOnly.length > 1 && !pathOnly.startsWith('//')) {
            newPathForDoubleSlash = '/' + pathOnly;
        } else if (lastSlashIdx > 0) {
            if (pathOnly[lastSlashIdx-1] !== '/') {
                 newPathForDoubleSlash = pathOnly.substring(0, lastSlashIdx) + '//' + pathOnly.substring(lastSlashIdx + 1);
            }
        }
        // Only add if it actually changed the path and is not same as original basePath
        if (newPathForDoubleSlash + query !== basePath && newPathForDoubleSlash !== pathOnly) {
             variations.push({ url: newPathForDoubleSlash + query, name: 'path_replace_with_double_slash' });
        }
    }
    return variations;
  },
];

/************************************************************
 * EXECUÇÃO PRINCIPAL
 ************************************************************/
/**
 * Função principal para executar os testes de bypass.
 * Itera pelos basePaths configurados, aplica diversas técnicas de bypass
 * e reporta os resultados.
 */
async function main() {
  if (CONFIG.verboseLevel >= 1) {
    console.log('[*] Iniciando testes de bypass WAF/Nginx...');
  }
  if (CONFIG.verboseLevel >= 2) {
    console.log('[*] Config:', JSON.stringify(CONFIG, null, 2)); // Pretty print config
  }

  const findings = [];
  let testsPerformed = 0;

  for (const basePath of CONFIG.basePaths) {
    if (CONFIG.verboseLevel >= 1) {
      console.log(`\n=== Testando path base: "${basePath}" ===`);
    }

    let originalStatusCode = null;
    const originalUrl = CONFIG.targetHost + basePath;
    const baselineMethod = 'GET';

    if (CONFIG.verboseLevel >= 1) {
      console.log(`[Base] Verificando URL original: ${baselineMethod} ${originalUrl}`);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), CONFIG.timeoutMs);
      const response = await fetch(originalUrl, {
        method: baselineMethod,
        headers: { ...CONFIG.extraHeaders },
        signal: controller.signal,
        redirect: 'manual',
      });
      clearTimeout(timeoutId);
      originalStatusCode = response.status;
      if (CONFIG.verboseLevel >= 1) {
        console.log(`[Base] URL original (${baselineMethod}): HTTP ${originalStatusCode}`);
      }
    } catch (error) {
      if (CONFIG.verboseLevel >= 0) {
        if (error.name === 'AbortError') {
            console.error(`[Base] Timeout ao buscar URL original ${originalUrl}`);
        } else {
            console.error(`[Base] Erro ao buscar URL original ${originalUrl}: ${error.message}`);
        }
      }
    }

    for (const techniqueGenerator of bypassTechniques) {
      const variations = techniqueGenerator(basePath);
      for (const variation of variations) {
        if (!variation || typeof variation.url !== 'string' || typeof variation.name !== 'string') {
            if(CONFIG.verboseLevel >=2) console.warn(`[!] Variação inválida ignorada de um gerador de técnica para basePath: ${basePath}`, variation);
            continue;
        }
        const { url: pathSuffix, name: techniqueName } = variation;
        for (const method of CONFIG.httpMethods) {
          testsPerformed++;
          const fullUrlToTest = CONFIG.targetHost + pathSuffix;
          const finding = await testUrl(fullUrlToTest, techniqueName, originalStatusCode, method);
          if (finding) {
            findings.push(finding);
          }
          if (CONFIG.requestDelayMs > 0) {
            await new Promise(resolve => setTimeout(resolve, CONFIG.requestDelayMs));
          }
        }
      }
    }
  }

  if (CONFIG.verboseLevel >= 0) {
    console.log('\n\n[*] Testes Concluídos.');
    console.log(`[*] Total de variações de URL testadas: ${testsPerformed}`);
    if (findings.length > 0) {
      console.log('\n[*] Resumo dos Achados Potenciais:');
      console.log('------------------------------------');
      findings.forEach(f => {
        const originalStatusDisplay = f.originalStatusCode !== null ? f.originalStatusCode : 'N/A';
        const commonLog = `TIPO: ${f.type} | TÉCNICA: ${f.techniqueName}\n    URL: ${f.method} ${f.url}\n    STATUS: Original ${originalStatusDisplay} -> Atual ${f.currentStatus}`;

        if (CONFIG.verboseLevel === 0) { // Quiet mode: very concise
            if (f.type === 'BYPASS' || f.type === 'SUCCESS_200_UNEXPECTED') {
                 console.log(`[+] ${f.type}: ${f.method} ${f.url} (Original ${originalStatusDisplay}, Atual ${f.currentStatus})`);
            }
        } else { // Normal (1) or Detailed (2)
            console.log(`[+] ${commonLog}`);
            if (CONFIG.verboseLevel >= 1 && (f.type === 'BYPASS' || f.type === 'SUCCESS_200_UNEXPECTED' || f.type === 'NGINX_400')) {
                if (f.bodySnippet) {
                    console.log('    CORPO (snippet):\n', f.bodySnippet);
                }
            }
            if (CONFIG.verboseLevel >= 2 && f.headers) {
                 console.log('    CABEÇALHOS:', f.headers);
            }
            console.log('------------------------------------');
        }
      });
      console.log(`\n[*] Total de achados potenciais no sumário: ${findings.length}`);
    } else {
      console.log('[*] Nenhum achado potencial de bypass direto ou sucesso inesperado no sumário.');
    }
  }
}

// Executa
main().catch(err => {
    console.error('[!] Erro fatal na execução principal:', err);
    if (CONFIG.verboseLevel >= 2 && err.stack) { // Print stack trace in verbose mode
        console.error(err.stack);
    }
    process.exit(1);
});
