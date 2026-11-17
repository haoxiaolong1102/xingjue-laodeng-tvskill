package com.xingjue.tvskill.setup;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

public final class InstallFileProvider extends ContentProvider {
    static final String APK_MIME_TYPE = "application/vnd.android.package-archive";
    private static final String AUTHORITY_SUFFIX = ".install";

    static Uri uriFor(String packageName, String assetName) {
        return new Uri.Builder().scheme("content").authority(packageName + AUTHORITY_SUFFIX)
                .appendPath(assetName).build();
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        return fileFor(uri) == null ? null : APK_MIME_TYPE;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        File file = fileFor(uri);
        if (file == null || !"r".equals(mode)) {
            throw new FileNotFoundException();
        }
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        File file = fileFor(uri);
        String[] columns = projection == null
                ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}
                : projection;
        MatrixCursor cursor = new MatrixCursor(columns, 1);
        if (file != null && file.isFile()) {
            MatrixCursor.RowBuilder row = cursor.newRow();
            for (String column : columns) {
                if (OpenableColumns.DISPLAY_NAME.equals(column)) {
                    row.add(file.getName());
                } else if (OpenableColumns.SIZE.equals(column)) {
                    row.add(file.length());
                } else {
                    row.add(null);
                }
            }
        }
        return cursor;
    }

    private File fileFor(Uri uri) {
        if (uri.getPathSegments().size() != 1) {
            return null;
        }
        String name = uri.getLastPathSegment();
        if ("tigris.apk".equals(name) || "marco-tv.apk".equals(name)) {
            return new File(getContext().getCacheDir(), name);
        }
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        throw new UnsupportedOperationException();
    }
}
