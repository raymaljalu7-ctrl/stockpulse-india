package com.stockpulse.india;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Color;

public class MainActivity extends Activity {
    // Cache-busted URL so each APK release loads the current StockPulse web UI.
    private static final String APP_URL = "https://stockpulse-india-web.onrender.com/?app=3.4.1";

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
        WebView w = findViewById(R.id.webview);
        if (w.canGoBack()) w.goBack(); else super.onBackPressed();
    }
}
