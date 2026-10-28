package com.xingjue.bridge;

import android.app.*;
import android.content.*;
import android.os.IBinder;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public final class BridgeService extends Service {
    public static volatile boolean ready;
    public static volatile String failure="";
    private ApiServer server;
    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel("local-connection","DpadTV 本机连接",NotificationManager.IMPORTANCE_LOW));
        Intent launch=new Intent(this,MainActivity.class);
        PendingIntent open=PendingIntent.getActivity(this,0,launch,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification notice=new Notification.Builder(this,"local-connection")
                .setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("DpadTV 本机连接已启动")
                .setContentText("使用已有片源，无需电脑常开").setContentIntent(open).setOngoing(true).build();
        startForeground(17919,notice);
        try(InputStream input=getAssets().open("default-sources.json");ByteArrayOutputStream output=new ByteArrayOutputStream()) {
            byte[] bytes=new byte[4096];int n;while((n=input.read(bytes))>=0)output.write(bytes,0,n);
            JSONObject config=new JSONObject(new String(output.toByteArray(),StandardCharsets.UTF_8));
            server=new ApiServer(config.getJSONArray("sources"));server.start(17919);ready=true;failure="";
        } catch(Exception error) {
            ready=false;failure=error.getClass().getSimpleName();android.util.Log.e("XingjueBridge","Cannot start local connection",error);stopSelf();
        }
    }
    @Override public int onStartCommand(Intent intent,int flags,int id){return START_STICKY;}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public void onDestroy(){ready=false;if(server!=null)try{server.close();}catch(Exception ignored){}super.onDestroy();}
}
