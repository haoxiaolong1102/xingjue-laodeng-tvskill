package com.xingjue.bridge;

import android.content.ComponentName;
import android.content.Intent;
import android.service.notification.NotificationListenerService;

/** Lifecycle callback only: does not inspect, log, or save notification contents. */
public final class RevivalListener extends NotificationListenerService {
    @Override public void onListenerConnected() {
        startForegroundService(new Intent(this,BridgeService.class));
    }
    @Override public void onListenerDisconnected() {
        requestRebind(new ComponentName(this,RevivalListener.class));
    }
}
