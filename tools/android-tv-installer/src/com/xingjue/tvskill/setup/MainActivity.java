package com.xingjue.tvskill.setup;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

public final class MainActivity extends Activity {
    private static final int BACKGROUND = 0xff11151d;
    private static final int SURFACE = 0xff1c2431;
    private static final int TEXT = 0xfff5f7fa;
    private static final int SUBTLE = 0xffb3bdcd;
    private static final int LIME = 0xffd8fa56;
    private static final int INSTALL_REQUEST = 1;

    private AppCard[] apps = new AppCard[0];
    private TextView status;
    private boolean preparing;
    private String installingAsset;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if (state != null) {
            installingAsset = state.getString("installingAsset");
        }
        try {
            apps = readApps();
        } catch (IOException | JSONException error) {
            Log.e("TvSkillSetup", "Could not read bundled application data", error);
        }
        setContentView(createScreen());
        refreshCards();
        if (apps.length > 0) {
            apps[0].button.requestFocus();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshCards();
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        state.putString("installingAsset", installingAsset);
        super.onSaveInstanceState(state);
    }

    private AppCard[] readApps() throws IOException, JSONException {
        String json;
        try (InputStream stream = getAssets().open("app-list.json");
             ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                bytes.write(buffer, 0, count);
            }
            json = new String(bytes.toByteArray(), StandardCharsets.UTF_8);
        }
        JSONArray list = new JSONArray(json);
        AppCard[] result = new AppCard[list.length()];
        for (int index = 0; index < list.length(); index++) {
            result[index] = new AppCard(list.getJSONObject(index));
        }
        return result;
    }

    private View createScreen() {
        ScrollView screen = new ScrollView(this);
        screen.setBackgroundColor(BACKGROUND);
        screen.setFillViewport(true);
        screen.setFocusable(false);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(38), dp(30), dp(38), dp(26));

        page.addView(label("星爵老灯讲AI  ·  安卓电视安装助手", 16, LIME, true));
        append(page, label(getString(com.xingjue.tvskill.setup.R.string.app_name), 34, TEXT, true), 6);
        append(page, label("选择要安装的应用，再用遥控器确认电视系统的提示。", 18, SUBTLE, false), 7);

        boolean wide = getResources().getConfiguration().screenWidthDp >= 700;
        LinearLayout cards = new LinearLayout(this);
        cards.setOrientation(wide ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        append(page, cards, 19);
        for (int index = 0; index < apps.length; index++) {
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    wide ? 0 : -1, -2, wide ? 1 : 0);
            if (index > 0 && wide) {
                params.leftMargin = dp(16);
            } else if (index > 0) {
                params.topMargin = dp(14);
            }
            cards.addView(createCard(apps[index]), params);
        }

        Button televisionSetup = button("桌面与广告设置");
        televisionSetup.setOnClickListener(view -> showTelevisionSetup());
        append(page, televisionSetup, 12);

        status = label(apps.length == 0 ? "安装包数据无法读取，请重新下载完整 APK。" :
                "安装包已内置，安装时可以离线。", 16, LIME, false);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        append(page, status, 14);

        TextView footer = label("欢迎使用我的第一个公开 Skill。用过有建议，欢迎到抖音「星爵老灯讲AI」留言、点个赞。", 15, SUBTLE, false);
        append(page, footer, 8);
        append(page, label("合流  heliuai.com", 14, SUBTLE, false), 6);
        screen.addView(page);
        return screen;
    }

    private View createCard(AppCard app) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(18), dp(16), dp(18), dp(16));
        card.setBackground(shape(SURFACE));
        card.addView(label(app.title, 24, TEXT, true));

        app.caption = label("", 15, LIME, false);
        append(card, app.caption, 5);
        append(card, label(app.description, 16, SUBTLE, false), 7);

        app.button = button("安装");
        app.button.setOnClickListener(view -> openOrInstall(app));
        append(card, app.button, 15);
        Button guide = button("设置说明");
        guide.setOnClickListener(view -> showMessage(app.title, app.guide));
        append(card, guide, 7);
        return card;
    }

    private void refreshCards() {
        for (AppCard app : apps) {
            if (app.button == null) {
                continue;
            }
            PackageInfo installed = installedApp(app.packageName);
            if (installed != null) {
                app.caption.setText("已安装  ·  " + installed.versionName);
                app.button.setText("打开应用");
                app.button.setEnabled(true);
            } else {
                boolean supported = app.supportsThisDevice();
                app.caption.setText("随包版本  " + app.version + (supported ? "" : "  ·  此设备不兼容"));
                app.button.setText("安装");
                app.button.setEnabled(supported);
            }
            app.button.setContentDescription(app.button.getText() + " " + app.title);
        }
    }

    private PackageInfo installedApp(String packageName) {
        try {
            return getPackageManager().getPackageInfo(packageName, 0);
        } catch (PackageManager.NameNotFoundException absent) {
            return null;
        }
    }

    private void openOrInstall(AppCard app) {
        if (preparing || installingAsset != null) {
            return;
        }
        if (installedApp(app.packageName) != null) {
            openApp(app);
            return;
        }
        if (!app.supportsThisDevice()) {
            return;
        }
        if (!getPackageManager().canRequestPackageInstalls()) {
            promptForInstallPermission();
            return;
        }
        preparing = true;
        status.setText("正在校验 " + app.title + "…");
        new Thread(() -> {
            try {
                stageVerifiedApk(app);
                runOnUiThread(() -> launchInstaller(app));
            } catch (IOException | NoSuchAlgorithmException error) {
                Log.e("TvSkillSetup", "Could not stage bundled APK", error);
                runOnUiThread(() -> {
                    preparing = false;
                    if (!isDestroyed()) {
                        status.setText("安装包校验或暂存失败。检查电视可用空间，或重新下载完整 APK。");
                    }
                });
            }
        }, "verify-bundled-apk").start();
    }

    private void openApp(AppCard app) {
        try {
            startActivity(new Intent(Intent.ACTION_MAIN).setClassName(app.packageName, app.activity));
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            Intent fallback = getPackageManager().getLeanbackLaunchIntentForPackage(app.packageName);
            if (fallback == null) {
                fallback = getPackageManager().getLaunchIntentForPackage(app.packageName);
            }
            if (fallback != null) {
                startActivity(fallback);
            } else {
                status.setText("请从电视应用列表打开 " + app.title + "。");
            }
        }
    }

    private void promptForInstallPermission() {
        new AlertDialog.Builder(this)
                .setTitle("电视需要安装授权")
                .setMessage("打开设置，允许「星爵老灯tvskill」安装应用，返回后再选择安装。")
                .setNegativeButton("返回", null)
                .setPositiveButton("打开设置", (dialog, which) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.fromParts("package", getPackageName(), null)));
                    } catch (ActivityNotFoundException | SecurityException unavailable) {
                        showMessage("电视安装设置", "请在电视设置的「账号与安全」或「安装未知应用」页面允许安装，返回后再试。");
                    }
                }).show();
    }

    private void stageVerifiedApk(AppCard app) throws IOException, NoSuchAlgorithmException {
        File target = new File(getCacheDir(), app.asset);
        File temporary = File.createTempFile("verify-", ".tmp", getCacheDir());
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try {
            try (InputStream input = getAssets().open("packages/" + app.asset);
                 FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] block = new byte[65536];
                int count;
                while ((count = input.read(block)) != -1) {
                    output.write(block, 0, count);
                    digest.update(block, 0, count);
                }
            }
            if (!MessageDigest.isEqual(digest.digest(), app.checksum)) {
                throw new IOException("Unexpected bundled APK checksum");
            }
            if (!temporary.renameTo(target)) {
                throw new IOException("Could not publish staged APK");
            }
        } finally {
            temporary.delete();
        }
    }

    private void launchInstaller(AppCard app) {
        preparing = false;
        if (isFinishing() || isDestroyed()) {
            new File(getCacheDir(), app.asset).delete();
            return;
        }
        Uri apk = InstallFileProvider.uriFor(getPackageName(), app.asset);
        Intent request = new Intent(Intent.ACTION_INSTALL_PACKAGE)
                .setData(apk)
                .putExtra(Intent.EXTRA_RETURN_RESULT, true)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        installingAsset = app.asset;
        status.setText("请在电视系统弹窗里选择是否安装。");
        try {
            startActivityForResult(request, INSTALL_REQUEST);
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            installingAsset = null;
            new File(getCacheDir(), app.asset).delete();
            status.setText("电视无法打开系统安装器，请查看电视的应用安装设置。");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == INSTALL_REQUEST && installingAsset != null) {
            new File(getCacheDir(), installingAsset).delete();
            revokeUriPermission(InstallFileProvider.uriFor(getPackageName(), installingAsset),
                    Intent.FLAG_GRANT_READ_URI_PERMISSION);
            installingAsset = null;
            refreshCards();
            status.setText(resultCode == RESULT_OK ? "安装完成，可打开应用。" : "已返回安装助手。");
        }
    }

    private void showTelevisionSetup() {
        new AlertDialog.Builder(this)
                .setTitle("桌面与广告设置")
                .setMessage("电视型号  " + Build.MODEL + "    Android " + Build.VERSION.RELEASE
                        + "\n\n先安装并打开 Tigris。调好后，按一次遥控器主页键确认能否回到大时钟。"
                        + "\n开机和静置广告的入口随固件不同，按电视提示单独确认。")
                .setNeutralButton("返回", null)
                .setNegativeButton("开机与静置广告", (dialog, which) -> showAdSetup())
                .setPositiveButton("设置大时钟桌面", (dialog, which) -> openHomeSettings())
                .show();
    }

    private void openHomeSettings() {
        if (startScreen(new Intent(Settings.ACTION_HOME_SETTINGS))) return;
        new AlertDialog.Builder(this)
                .setTitle("通过 Tigris 设置桌面")
                .setMessage("这台电视未开放通用默认主页设置。打开 Tigris 的主屏幕设置，按机型检查桌面守护，再用遥控器主页键验证。")
                .setNegativeButton("返回", null)
                .setPositiveButton("打开主屏幕设置", (dialog, which) -> {
                    Intent settings = new Intent(Intent.ACTION_MAIN)
                            .setClassName("com.leslie.tvhome", "com.leslie.tvhome.SettingsActivity");
                    if (!startScreen(settings)) {
                        showMessage("先安装 Tigris", "回安装助手选择 Tigris 大时钟桌面，完成系统安装后再来设置。");
                    }
                }).show();
    }

    private void showAdSetup() {
        new AlertDialog.Builder(this)
                .setTitle("开机和静置广告")
                .setMessage("在电视系统设置中查找「系统广告」或「开机广告」。若有明确开关，可按系统提示设置。"
                        + "\n\n若静置后出现相框广告，可在相应机型的屏保或自动相册计时设置里调整。"
                        + "\n\n若固件隐藏入口，请按星爵老灯tvskill的机型教程处理，先记录原值。")
                .setNegativeButton("返回", null)
                .setNeutralButton("机型教程", (dialog, which) -> openFirmwareGuide())
                .setPositiveButton("打开系统入口", (dialog, which) -> {
                    Intent official = new Intent("mitv.intent.action.ACCOUNT_AUTH_MANAGER")
                            .setPackage("com.mitv.tvhome");
                    if (!startScreen(official) && !startScreen(new Intent(Settings.ACTION_SETTINGS))) {
                        showMessage("从遥控器进入电视设置",
                                "按遥控器设置键，或回原厂首页打开设置。若看不到对应开关，请查机型教程。");
                    }
                }).show();
    }

    private void openFirmwareGuide() {
        String url = "https://github.com/haoxiaolong1102/xingjue-laodeng-tvskill";
        if (!startScreen(new Intent(Intent.ACTION_VIEW, Uri.parse(url)))) {
            showMessage("在手机或电脑查看机型教程", url);
        }
    }

    private boolean startScreen(Intent intent) {
        try {
            startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            return false;
        }
    }

    private void showMessage(String title, String message) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(message)
                .setPositiveButton("返回", null).show();
    }

    private void append(LinearLayout parent, View child, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(top);
        parent.addView(child, params);
    }

    private TextView label(String text, int size, int color, boolean bold) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextSize(size);
        label.setTextColor(color);
        if (bold) {
            label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        }
        return label;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(17);
        button.setAllCaps(false);
        button.setMinHeight(dp(42));
        button.setGravity(Gravity.CENTER);
        button.setBackgroundTintList(null);
        int[][] states = {{-android.R.attr.state_enabled}, {android.R.attr.state_focused}, {}};
        StateListDrawable background = new StateListDrawable();
        background.addState(states[0], shape(0xff222a37));
        background.addState(states[1], shape(LIME));
        background.addState(states[2], shape(0xff303a49));
        button.setBackground(background);
        button.setTextColor(new ColorStateList(states, new int[]{SUBTLE, Color.BLACK, TEXT}));
        button.setPadding(dp(12), dp(7), dp(12), dp(7));
        return button;
    }

    private GradientDrawable shape(int color) {
        GradientDrawable surface = new GradientDrawable();
        surface.setColor(color);
        surface.setCornerRadius(dp(12));
        return surface;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static final class AppCard {
        final String title;
        final String description;
        final String guide;
        final String packageName;
        final String activity;
        final String version;
        final String asset;
        final byte[] checksum;
        final int minSdk;
        final String[] abis;
        TextView caption;
        Button button;

        AppCard(JSONObject data) throws JSONException {
            title = data.getString("title");
            description = data.getString("description");
            guide = data.getString("guide");
            packageName = data.getString("package");
            activity = data.getString("activity");
            version = data.getString("version");
            asset = data.getString("asset");
            minSdk = data.getInt("minSdk");
            String sha256 = data.getString("sha256");
            checksum = new byte[32];
            for (int index = 0; index < checksum.length; index++) {
                checksum[index] = (byte) Integer.parseInt(sha256.substring(index * 2, index * 2 + 2), 16);
            }
            JSONArray appAbis = data.getJSONArray("abis");
            abis = new String[appAbis.length()];
            for (int index = 0; index < abis.length; index++) {
                abis[index] = appAbis.getString(index);
            }
        }

        boolean supportsThisDevice() {
            if (Build.VERSION.SDK_INT < minSdk) {
                return false;
            }
            if (abis.length == 0) {
                return true;
            }
            for (String abi : Build.SUPPORTED_ABIS) {
                if (Arrays.asList(abis).contains(abi)) {
                    return true;
                }
            }
            return false;
        }
    }
}
