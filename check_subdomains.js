const axios = require('axios');

// Função para verificar subdomínios
async function checkSubdomain(subdomain, baseDomain) {
    const url = `https://${subdomain}.${baseDomain}`;
    try {
        await axios.get(url, { timeout: 5000 }); // We only care if the request succeeds or fails
        return {
            subdomain: subdomain,
            url: url,
            status: 'active',
            errorMessage: null
        };
    } catch (error) {
        // It's useful to distinguish between a timeout and other errors if possible,
        // but for now, we'll keep it simple.
        // Axios errors have a `isAxiosError` property.
        // A timeout error specifically might have `error.code === 'ECONNABORTED'`.
        return {
            subdomain: subdomain,
            url: url,
            status: 'error', // Or more specific like 'timeout', 'dns_error', 'http_error_404' etc.
            errorMessage: error.message
        };
    }
}

(async () => {
    // Default values
    let baseDomain = 'api2.grofers.com';
    let subdomains = ['www', 'api', 'mail', 'blog', 'dev', 'support', 'shop'];

    // Check for command-line arguments
    // process.argv[0] is 'node', process.argv[1] is the script path
    if (process.argv[2]) {
        baseDomain = process.argv[2];
    }

    if (process.argv[3]) {
        subdomains = process.argv[3].split(',');
    }

    console.log(`Checking subdomains for base domain: ${baseDomain}`);
    console.log(`Subdomains to check: ${subdomains.join(', ')}`);


    // Create an array of promises
    const promises = subdomains.map(subdomain => {
        return checkSubdomain(subdomain, baseDomain);
    });

    const results = await Promise.allSettled(promises);

    console.log("\n--- Scan Results ---");
    results.forEach(result => {
        if (result.status === 'fulfilled') {
            const data = result.value; // This is the object returned by checkSubdomain
            let output = `[${data.url}] - Status: ${data.status}`;
            if (data.errorMessage) {
                output += ` (Error: ${data.errorMessage})`;
            }
            console.log(output);
        } else {
            // This case should ideally not be reached if checkSubdomain handles its own errors
            console.error(`Unexpected error for a subdomain check: ${result.reason}`);
        }
    });
})();
