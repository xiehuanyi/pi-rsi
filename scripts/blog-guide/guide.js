/* Guide links: select a node or Wiki entry in the interactive view next to the text.
   Buttons carry data-jump-node / data-jump-claim; #node=<id> and #claim=<id> deep-link on load. */
(() => {
  const behavior = () => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth');
  const reveal = el => el && el.scrollIntoView({behavior: behavior(), block: 'start'});

  function showNode(id) {
    const key = CSS.escape(id);
    // Overview: chip in the compact branch view; selection also updates the chart ring and detail card.
    const chip = document.querySelector(`#rsi-tree button[data-node="${key}"]`);
    if (chip) { chip.click(); reveal(document.getElementById('rsi-fig-tree')); return true; }
    // Full explorer: the ledger button selects, centres the tree camera and reveals the inspector.
    const row = document.querySelector(`#table [data-select="${key}"]`);
    if (row) { row.click(); return true; }
    const card = document.querySelector(`#tree .node[data-id="${key}"]`);
    if (card) {
      card.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      reveal(document.querySelector('.rsi-native .inspector') || card);
      return true;
    }
    return false;
  }

  function showClaim(id) {
    const select = document.getElementById('wk-claim');
    if (!select || ![...select.options].some(o => o.value === id)) return false;
    select.value = id;
    select.dispatchEvent(new Event('change', {bubbles: true}));
    reveal(document.getElementById('pi-rsi-wiki-oct04'));
    return true;
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-jump-node],[data-jump-claim]');
    if (!button) return;
    if (button.dataset.jumpNode) showNode(button.dataset.jumpNode);
    else showClaim(button.dataset.jumpClaim);
  });

  function fromHash() {
    const match = /^#(node|claim)=([\w.-]+)$/.exec(location.hash);
    if (match) (match[1] === 'node' ? showNode : showClaim)(decodeURIComponent(match[2]));
  }
  window.addEventListener('load', fromHash);
  window.addEventListener('hashchange', fromHash);
})();
