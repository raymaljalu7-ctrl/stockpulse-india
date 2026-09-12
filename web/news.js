(function(){
  const NEWS_PROXY='https://api.rss2json.com/v1/api.json?rss_url=';
  const NEWS_BASE='https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q=';
  const esc=s=>String(s||'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m]));
  const cleanTitle=s=>String(s||'').replace(/\s+-\s+[^-]+$/,'');
  async function feed(symbol, query){
    const rss=NEWS_BASE+encodeURIComponent(symbol+' '+query);
    const r=await fetch(NEWS_PROXY+encodeURIComponent(rss));
    if(!r.ok) throw Error('news '+r.status);
    const d=await r.json();
    return (d.items||[]).slice(0,10).map(x=>({title:cleanTitle(x.title),link:x.link,date:x.pubDate,source:x.author||d.feed?.title||'News'}));
  }
  function newsBlock(items, empty){
    if(!items.length) return '<div class="newsEmpty">'+empty+'</div>';
    return '<div class="newsList">'+items.map(n=>'<a class="newsItem" href="'+esc(n.link)+'" target="_blank" rel="noopener"><b>'+esc(n.title)+'</b><span>'+esc(n.source)+' • '+new Date(n.date).toLocaleString('en-IN')+'</span></a>').join('')+'</div>';
  }
  window.loadStockNews=async function(symbol){
    const box=document.getElementById('stockNews'); if(!box)return;
    box.innerHTML='<div class="newsLoading">Loading latest news and announcements…</div>';
    try{
      const [all,ann,biz]=await Promise.allSettled([feed(symbol,''),feed(symbol,'announcement filing exchange'),feed(symbol,'results earnings order contract business')]);
      const allItems=all.status==='fulfilled'?all.value:[];
      const annItems=ann.status==='fulfilled'?ann.value:[];
      const bizItems=biz.status==='fulfilled'?biz.value:[];
      box.innerHTML='<div class="newsTabs"><button class="newsTab active" data-n="all">All News</button><button class="newsTab" data-n="ann">Announcements</button><button class="newsTab" data-n="biz">Business</button></div><div id="newsContent">'+newsBlock(allItems,'No recent news found.')+'</div>';
      const sets={all:allItems,ann:annItems,biz:bizItems};
      box.querySelectorAll('.newsTab').forEach(b=>b.onclick=()=>{box.querySelectorAll('.newsTab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById('newsContent').innerHTML=newsBlock(sets[b.dataset.n],b.dataset.n==='ann'?'No recent company announcements found.':'No recent news found.')});
    }catch(e){
      box.innerHTML='<div class="newsEmpty">News service is temporarily unavailable. <a target="_blank" rel="noopener" href="https://news.google.com/search?q='+encodeURIComponent(symbol)+'">Open latest '+esc(symbol)+' news</a></div>';
    }
  };
  const original=window.openDetail;
  window.openDetail=function(symbol){
    original(symbol);
    const body=document.getElementById('detailBody');
    if(!body || document.getElementById('stockNews')) return;
    body.insertAdjacentHTML('beforeend','<section id="stockNews" class="stockNews"><h3>Latest news & announcements</h3><div class="newsLoading">Loading…</div></section>');
    window.loadStockNews(symbol);
  };
})();
