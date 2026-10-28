package com.xingjue.bridge;

import android.app.Activity;
import android.os.*;
import android.content.*;
import android.graphics.Color;
import android.widget.*;

public final class MainActivity extends Activity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private TextView status;
    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(64,48,64,48);
        layout.setBackgroundColor(Color.rgb(11,17,28));
        TextView title=new TextView(this);title.setText("LibreTV 本机连接");title.setTextColor(Color.WHITE);title.setTextSize(28);layout.addView(title);
        TextView description=new TextView(this);description.setText("为原 DpadTV 提供本机连接，继续使用已有公开片源。\n服务在电视里运行，无需电脑常开。");description.setTextColor(Color.LTGRAY);description.setTextSize(18);description.setPadding(0,24,0,24);layout.addView(description);
        status=new TextView(this);status.setTextColor(Color.WHITE);status.setTextSize(18);layout.addView(status);
        Button start=new Button(this);start.setText("启动并打开 DpadTV");start.setOnClickListener(v->startAndOpen());layout.addView(start);
        Button stop=new Button(this);stop.setText("停止本机连接");stop.setOnClickListener(v->{stopService(new Intent(this,BridgeService.class));status.setText("本机连接已停止。需要使用时请重新启动。");});layout.addView(stop);
        setContentView(layout);start.requestFocus();startAndOpen();
    }
    private void startAndOpen() {
        status.setText("正在启动本机连接…");
        startForegroundService(new Intent(this,BridgeService.class));
        waitForService(0);
    }
    private void waitForService(int attempt) {
        handler.postDelayed(()->{
            if(isFinishing())return;
            if(BridgeService.ready){
                status.setText("本机连接已启动");
                Intent app=getPackageManager().getLaunchIntentForPackage("com.dpadtv.client");
                if(app==null)app=getPackageManager().getLeanbackLaunchIntentForPackage("com.dpadtv.client");
                if(app!=null){startActivity(app);finish();}else status.setText("请先安装 DpadTV 客户端。");
            } else if(attempt<12)waitForService(attempt+1);
            else status.setText("本机连接未能启动，请重新尝试。"+(BridgeService.failure.isEmpty()?"":"（"+BridgeService.failure+"）"));
        },250);
    }
    @Override public void onDestroy(){handler.removeCallbacksAndMessages(null);super.onDestroy();}
}
