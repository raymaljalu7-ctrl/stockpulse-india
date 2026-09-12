package com.stockpulse.india;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Color;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://stockpulse-india-web.onrender.com/?app=3.4.3";

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        WebView w = findViewById(R.id.webview);
        w.setBackgroundColor(Color.WHITE);
        w.setWebViewClient(new WebViewClient());
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        w.loadUrl(APP_URL);
    }

    @Override public void onBackPressed() {
        final WebView w = findViewById(R.id.webview);
        w.evaluateJavascript(
            "(function(){" +
            "var p=['home','screen','watch','market','portfolio','alerts'];" +
            "var cur=p.find(function(id){var e=document.getElementById(id);return e&&!e.classList.contains('hidden');});" +
            "if(cur&&cur!=='home'&&window.setTab){window.setTab('home');return 'handled';}" +
            "return 'exit';" +
            "})()",
            value -> { if (\"\\\"exit\\\"\".equals(value)) super.onBackPressed(); }
        );
    }
}
