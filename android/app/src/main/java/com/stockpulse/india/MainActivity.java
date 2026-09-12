package com.stockpulse.india;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://stockpulse-india-web.onrender.com/?app=4.1";
    private WebView webView;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        webView = findViewById(R.id.webview);
        webView.setBackgroundColor(Color.WHITE);
        webView.setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                injectNavigation(view);
            }
        });
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webView.clearCache(true);
        webView.loadUrl(APP_URL);
    }

    private void injectNavigation(WebView view) {
        String js = "(function(){" +
            "if(document.getElementById('spNativeNav'))return;" +
            "var m=document.querySelector('main');if(!m)return;" +
            "var n=document.createElement('div');n.id='spNativeNav';" +
            "n.style.cssText='display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:0 0 14px;padding:0;';" +
            "var items=[['⌂','Dashboard','home'],['⌕','Screener','screen'],['★','Watchlist','watch'],['▣','Portfolio','portfolio'],['♢','Alerts','alerts'],['◈','Live Market','market']];" +
            "items.forEach(function(x){var b=document.createElement('button');b.type='button';b.innerHTML='<span style=\\\"font-size:16px;display:block\\\">'+x[0]+'</span><span style=\\\"font-size:10px\\\">'+x[1]+'</span>';b.style.cssText='min-height:54px;border-radius:10px;border:1px solid #263650;background:#111c2d;color:#dce5ef;font-weight:800;';b.onclick=function(){if(window.setTab)window.setTab(x[2]);};n.appendChild(b);});" +
            "var h=m.querySelector('.appHeader');if(h)h.insertAdjacentElement('afterend',n);else m.insertBefore(n,m.firstChild);" +
            "})()";
        view.evaluateJavascript(js, null);
    }

    @Override public void onBackPressed() {
        webView.evaluateJavascript(
            "(function(){var p=['home','screen','watch','market','portfolio','alerts'];var cur=p.find(function(id){var e=document.getElementById(id);return e&&!e.classList.contains('hidden');});if(cur&&cur!=='home'&&window.setTab){window.setTab('home');return 'handled';}return 'exit';})()",
            value -> { if ("\"exit\"".equals(value)) finish(); }
        );
    }
}
