package com.stockpulse.india;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final String APP_URL = "file:///android_asset/index.html";
    private WebView webView;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        webView = findViewById(R.id.webview);
        webView.setBackgroundColor(Color.rgb(11,16,32));
        webView.setWebViewClient(new WebViewClient());
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        webView.clearCache(true);
        webView.loadUrl(APP_URL);
    }

    @Override public void onBackPressed() {
        webView.evaluateJavascript(
            "(function(){var m=document.getElementById('modal');if(m&&!m.classList.contains('hide')){m.classList.add('hide');return 'handled';}var p=['home','screen','watch','market'];for(var i=1;i<p.length;i++){var e=document.getElementById(p[i]);if(e&&!e.classList.contains('hide')){document.getElementById(p[i]).classList.add('hide');document.getElementById('home').classList.remove('hide');return 'handled';}}return 'exit';})()",
            value -> { if ("\"exit\"".equals(value)) finish(); }
        );
    }
}
