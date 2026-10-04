/* Public viewer state is local to this browser; no host API or model calls. */
(() => {
  const key='rsi-view:'+location.pathname;
  let state=null;
  try { state=JSON.parse(localStorage.getItem(key)); } catch {}
  window.openai={
    widgetState:state,
    setWidgetState(next){
      this.widgetState=next;
      try { localStorage.setItem(key,JSON.stringify(next)); } catch {}
      return Promise.resolve();
    }
  };
  document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('.rsi-viz .pp-select select').forEach(select=>{
      const descriptor=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value');
      const sync=()=>{
        const label=select.closest('.pp-select').querySelector('.pp-select__button > span');
        if(label)label.textContent=select.selectedOptions[0]?.textContent||'';
      };
      Object.defineProperty(select,'value',{configurable:true,get(){return descriptor.get.call(this);},set(value){descriptor.set.call(this,value);sync();}});
      select.addEventListener('change',sync);sync();
    });
  });
})();
