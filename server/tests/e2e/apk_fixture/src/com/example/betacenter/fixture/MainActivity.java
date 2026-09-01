package com.example.betacenter.fixture;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.TextView;

/** A deliberately tiny launcher activity used only by the server end-to-end suite. */
public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        TextView message = new TextView(this);
        message.setBackgroundColor(Color.rgb(244, 247, 252));
        message.setGravity(Gravity.CENTER);
        message.setText("Beta Center\nAPK fixture 1.0.0");
        message.setTextColor(Color.rgb(28, 39, 55));
        message.setTextSize(22.0f);
        setContentView(message);
    }
}
