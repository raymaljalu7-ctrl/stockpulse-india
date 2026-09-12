(function(){
  const NEWS_PROXY='https://api.rss2json.com/v1/api.json?rss_url=';
  const NEWS_BASE='https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q=';
  const esc=s=>String(s||'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m]));
  const cleanTitle=s=>String(s||'').replace(/\s+-\s+[^-]+$/,'');
  const uniq=a=>{const seen=new Set();return a.filter(x=>{const k=(x.title||'').toLowerCase();if(seen.has(k))return false;seen.add(k);return true})};
  const recommendationWords=/\b(buy|sell|hold|upgrade|downgrade|target price|price target|outperform|underperform|brokerage|analyst|rating|accumulate|reduce)\b/i;
  const catalystWords=/\b(results|earnings|revenue|profit|order|contract|deal|approval|capex|dividend|bonus|split|buyback|acquisition|merger|guidance|expansion|plant|launch)\b/i;
  const filingWords=/\b(nse|bse|sebi|filing|exchange|disclosure|announcement|regulatory|corporate announcement)\b/i;
  async function feed(symbol, query){
    const rss=NEWS_BASE+encodeURIComponent(symbol+' '+query);
    const r=await fetch(NEWS_PROXY+encodeURIComponent(rss));
    if(!r.ok) throw Error('news '+r.status);
    const d=await r.json();
    return (d.items||[]).slice(0,20).map(x=>({title:cleanTitle(x.title),link:x.link,date:x.pubDate,source:x.author||d.feed?.title||'News'}));
  }
  function classify(items){return uniq(items).map(n=>({...n,type:recommendationWords.test(n.title)?'Recommendation':filingWords.test(n.title)?'Filing / Announcement':catalystWords.test(n.title)?'Catalyst':'Market News'}));}
  function newsBlock(items, empty){
    if(!items.length) return '<div class="newsEmpty">'+empty+'</div>';
    return '<div class="newsList">'+items.map(n=>'<a class="newsItem" href="'+esc(n.link)+'" target="_blank" rel="noopener"><b>'+esc(n.title)+'</b><span><em>'+esc(n.type||'News')+'</em> '+esc(n.source)+' • '+new Date(n.date).toLocaleString('en-IN')+'</span></a>').join('')+'</div>';
  }
  window.loadStockNews=async function(symbol){
    const box=document.getElementById('stockNews'); if(!box)return;
    box.innerHTML='<div class="newsLoading">Collecting A-to-Z news, filings and market information…</div>';
    try{
      const queries=['','NSE BSE SEBI filing announcement disclosure exchange','results earnings revenue profit guidance','buy sell target price brokerage analyst upgrade downgrade','order contract deal partnership capex acquisition expansion','dividend bonus split buyback corporate action','regulatory legal approval management promoter','stock market sector industry outlook'];
      const results=await Promise.allSettled(queries.map(q=>feed(symbol,q)));
      const merged=classify(uniq(results.flatMap(r=>r.status==='fulfilled'?r.value:[])));
      const rec=merged.filter(x=>x.type==='Recommendation');
      const filings=merged.filter(x=>x.type==='Filing / Announcement');
      const catalysts=merged.filter(x=>x.type==='Catalyst');
      const market=merged.filter(x=>x.type==='Market News');
      const sets={all:merged,recommendation:rec,filings,catalysts,market};
      box.innerHTML='<div class="newsTabs"><button class="newsTab active" data-n="all">All News</button><button class="newsTab" data-n="recommendation">Recommendations</button><button class="newsTab" data-n="filings">NSE/BSE/SEBI</button><button class="newsTab" data-n="catalysts">Company/Catalysts</button><button class="newsTab" data-n="market">Market</button></div><div class="newsSummary"><b>'+merged.length+'</b> relevant items collected • recommendations '+rec.length+' • filings '+filings.length+' • catalysts '+catalysts.length+'</div><div id="newsContent">'+newsBlock(merged,'No recent news found.')+'</div>';
      box.querySelectorAll('.newsTab').forEach(b=>b.onclick=()=>{box.querySelectorAll('.newsTab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById('newsContent').innerHTML=newsBlock(sets[b.dataset.n],b.dataset.n==='recommendation'?'No explicit recommendation-related news found.':b.dataset.n==='filings'?'No recent filing/announcement news found.':'No recent news found.')});
    }catch(e){
      box.innerHTML='<div class="newsEmpty">News collection is temporarily unavailable. <a target="_blank" rel="noopener" href="https://news.google.com/search?q='+encodeURIComponent(symbol)+'">Open latest '+esc(symbol)+' news</a></div>';
    }
  };
  const original=window.openDetail;
  window.openDetail=function(symbol){
    original(symbol);
    const body=document.getElementById('detailBody');
    if(!body || document.getElementById('stockNews')) return;
    body.insertAdjacentHTML('beforeend','<section id="stockNews" class="stockNews"><h3>A-to-Z news & market intelligence</h3><div class="newsLoading">Loading…</div></section>');
    window.loadStockNews(symbol);
  };
})();
