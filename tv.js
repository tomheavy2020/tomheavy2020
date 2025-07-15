// Lista de canais legais
const canais = [
  {
    numero: 1,
    nome: "SBT",
    url: "https://www.youtube.com/embed/ABVQXgr2LW4?autoplay=1",
    embeddable: true
  }
];

let canalAtual = -1;
let tvLigada = false;
let mudandoCanal = false;

// Cria a grade de canais
function criarGradeCanais() {
  const grid = document.getElementById('channels-grid');

  canais.forEach((canal, index) => {
    const btn = document.createElement('button');
    btn.className = 'channel-btn';
    btn.innerHTML = `CH ${canal.numero}<br><small>${canal.nome}</small>`;
    btn.onclick = () => sintonizarCanal(index);
    grid.appendChild(btn);
  });
}

// Liga/Desliga TV
function ligarDesligar() {
  const screen = document.getElementById('tv-screen');
  const content = document.getElementById('tv-content');
  const display = document.getElementById('channel-display');

  if (!tvLigada) {
    // Liga a TV
    tvLigada = true;
    screen.style.animation = 'tv-on 0.5s ease-out';

    // Adiciona animação de ligar
    setTimeout(() => {
      screen.style.animation = '';
      if (canalAtual === -1) {
        canalAtual = 0;
      }
      sintonizarCanal(canalAtual);
    }, 500);
  } else {
    // Desliga a TV
    tvLigada = false;
    screen.style.animation = 'tv-off 0.3s ease-out';

    setTimeout(() => {
      content.innerHTML = `
        <div class="no-signal">
          <div style="font-size: 3em;">📺</div>
          <div>DESLIGADO</div>
        </div>
      `;
      display.textContent = '--';
      screen.style.animation = '';
      atualizarBotoesCanais(-1);
    }, 300);
  }
}

// Muda canal
function mudarCanal(direcao) {
  if (!tvLigada) {
    ligarDesligar();
    return;
  }

  let novoCanal = canalAtual + direcao;

  if (novoCanal < 0) {
    novoCanal = canais.length - 1;
  } else if (novoCanal >= canais.length) {
    novoCanal = 0;
  }

  sintonizarCanal(novoCanal);
}

// Sintoniza canal específico
function sintonizarCanal(index) {
  if (!tvLigada) {
    ligarDesligar();
    setTimeout(() => sintonizarCanal(index), 600);
    return;
  }

  if (mudandoCanal) return;

  mudandoCanal = true;
  canalAtual = index;

  const canal = canais[index];
  const content = document.getElementById('tv-content');
  const display = document.getElementById('channel-display');
  const staticEl = document.getElementById('static');

  // Mostra estática
  staticEl.classList.add('show');
  content.style.opacity = '0';

  // Atualiza display
  display.textContent = `CH ${canal.numero}`;

  // Simula mudança de canal
  setTimeout(() => {
    content.innerHTML = `
      <iframe
        src="${canal.url}"
        allowfullscreen
        allow="autoplay; fullscreen">
      </iframe>
    `;

    setTimeout(() => {
      staticEl.classList.remove('show');
      content.style.opacity = '1';
      mudandoCanal = false;
    }, 300);
  }, 500);

  atualizarBotoesCanais(index);
}

// Atualiza visual dos botões
function atualizarBotoesCanais(indexAtivo) {
  const botoes = document.querySelectorAll('.channel-btn');
  botoes.forEach((btn, index) => {
    if (index === indexAtivo) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

// Efeito de volume (decorativo)
document.querySelector('.volume-knob').addEventListener('click', function() {
  this.style.transform = 'rotate(' + (Math.random() * 360) + 'deg)';
});

// Animações CSS adicionais
const style = document.createElement('style');
style.textContent = `
  @keyframes tv-on {
    0% {
      transform: scale(0, 0.01);
      filter: brightness(3);
    }
    50% {
      transform: scale(1, 0.01);
    }
    100% {
      transform: scale(1, 1);
      filter: brightness(1);
    }
  }

  @keyframes tv-off {
    0% {
      transform: scale(1, 1);
      filter: brightness(1);
    }
    50% {
      transform: scale(1, 0.01);
      filter: brightness(2);
    }
    100% {
      transform: scale(0, 0.01);
      filter: brightness(0);
    }
  }

  /* Efeito de brilho da tela */
  .tv-screen::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(
      ellipse at center,
      rgba(255,255,255,0.1) 0%,
      transparent 50%
    );
    pointer-events: none;
    animation: flicker 0.15s infinite;
  }

  @keyframes flicker {
    0% { opacity: 0.95; }
    50% { opacity: 1; }
    100% { opacity: 0.98; }
  }

  /* Reflexo na tela */
  .tv-screen-container::after {
    content: '';
    position: absolute;
    top: 10%;
    left: 10%;
    width: 30%;
    height: 30%;
    background: radial-gradient(
      ellipse at top left,
      rgba(255,255,255,0.1) 0%,
      transparent 50%
    );
    border-radius: 50%;
    transform: rotate(-45deg);
    pointer-events: none;
  }
`;
document.head.appendChild(style);

// Inicializa
criarGradeCanais();

// Som de ligar TV (simulado com vibração se disponível)
function somTV() {
  if ('vibrate' in navigator) {
    navigator.vibrate(50);
  }
}

// Adiciona som aos botões
document.querySelectorAll('.control-btn').forEach(btn => {
  btn.addEventListener('click', somTV);
});
