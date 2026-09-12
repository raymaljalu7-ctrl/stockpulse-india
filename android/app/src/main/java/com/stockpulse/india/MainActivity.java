package com.stockpulse.india;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Color;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://stockpulse-india-web.onrender.com/?app=3.3";
    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        WebView w = findViewById(R.id.webview);
        w.setBackgroundColor(Color.rgb(8,16,29));
        w.setWebViewClient(new WebViewClient());
        WebSettings s = w.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        w.clearCache(true);
        w.loadUrl(APP_URL);
    }
    @Override public void onBackPressed() {
        WebView w = findViewById(R.id.webview);
        if (w.canGoBack()) w.goBack(); else super.onBackPressed();
    }
}
