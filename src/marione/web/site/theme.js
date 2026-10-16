// Caricato in <head> (sincrono) per evitare il flash del tema sbagliato.
(function () {
  var t = null;
  try { t = localStorage.getItem('marione-theme'); } catch (e) { /* storage bloccato */ }
  if (t !== 'dark' && t !== 'light') {
    t = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', t);
})();
