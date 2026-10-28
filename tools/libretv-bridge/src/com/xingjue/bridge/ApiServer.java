package com.xingjue.bridge;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Loopback-only compatibility API for the existing DpadTV client. */
public final class ApiServer implements Closeable {
    private static final int MAX_BODY = 512 * 1024;
    private static final int MAX_UPSTREAM = 8 * 1024 * 1024;
    private static final String UA = "Mozilla/5.0 (Linux; Android 9) AppleWebKit/537.36 Chrome/120.0 Safari/537.36";
    private final JSONArray defaults;
    private final ExecutorService clients = new ThreadPoolExecutor(4, 10, 30, TimeUnit.SECONDS,
            new ArrayBlockingQueue<Runnable>(48), new ThreadPoolExecutor.AbortPolicy());
    private final ExecutorService searches = Executors.newFixedThreadPool(3);
    private final Map<String, Cached> cache = Collections.synchronizedMap(new LinkedHashMap<String, Cached>(32, .75f, true) {
        protected boolean removeEldestEntry(Map.Entry<String, Cached> e) { return size() > 24; }
    });
    private ServerSocket listener;
    private Thread thread;
    private volatile boolean running;

    private static final class Cached {
        final long at = System.currentTimeMillis(); final String text;
        Cached(String text) { this.text = text; }
    }
    private static final class Reply {
        final int status; final byte[] body; final String type;
        Reply(int status, byte[] body, String type) { this.status = status; this.body = body; this.type = type; }
    }

    public ApiServer(JSONArray defaults) { this.defaults = defaults; }

    public synchronized void start(int port) throws IOException {
        if (running) return;
        listener = new ServerSocket();
        listener.setReuseAddress(true);
        listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), port), 32);
        running = true;
        thread = new Thread(() -> {
            while (running) {
                try {
                    final Socket socket = listener.accept();
                    try { clients.execute(() -> serve(socket)); }
                    catch (RejectedExecutionException busy) { socket.close(); }
                } catch (IOException error) { if (running) System.err.println("bridge accept: " + error.getClass().getSimpleName()); }
            }
        }, "libretv-loopback");
        thread.start();
        System.out.println("READY loopback port=" + port);
    }

    private void serve(Socket socket) {
        String path = "unknown";
        long started = System.currentTimeMillis();
        try (Socket connection = socket) {
            connection.setSoTimeout(12000);
            InputStream input = connection.getInputStream();
            ByteArrayOutputStream header = new ByteArrayOutputStream();
            int tail = 0;
            while (header.size() < 32768) {
                int c = input.read();
                if (c < 0) return;
                header.write(c); tail = (tail << 8) | c;
                if (tail == 0x0d0a0d0a) break;
            }
            String[] lines = new String(header.toByteArray(), StandardCharsets.ISO_8859_1).split("\r\n");
            String[] first = lines[0].split(" ");
            if (first.length != 3 || !first[1].startsWith("/")) throw new IOException("Malformed HTTP request");
            int length = 0;
            for (int i = 1; i < lines.length; i++) {
                if (lines[i].toLowerCase(Locale.ROOT).startsWith("content-length:")) length = Integer.parseInt(lines[i].substring(15).trim());
                if (lines[i].toLowerCase(Locale.ROOT).startsWith("transfer-encoding:")) throw new IOException("Chunked request not supported");
            }
            if (length < 0 || length > MAX_BODY) throw new IOException("Request too large");
            byte[] body = new byte[length]; int offset = 0;
            while (offset < length) { int n = input.read(body, offset, length-offset); if (n < 0) throw new EOFException(); offset += n; }
            URI uri = new URI(first[1]); path = uri.getPath();
            Map<String,String> query = query(uri.getRawQuery());
            Reply reply;
            try { reply = route(first[0], path, query, new String(body, StandardCharsets.UTF_8)); }
            catch (Exception error) {
                String message = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
                reply = new Reply(502, ("{\"error\":"+JSONObject.quote(message)+"}").getBytes(StandardCharsets.UTF_8), "application/json; charset=utf-8");
            }
            String status = reply.status == 200 ? "OK" : reply.status == 404 ? "Not Found" : "Bad Gateway";
            OutputStream output = connection.getOutputStream();
            output.write(("HTTP/1.1 "+reply.status+" "+status+"\r\nContent-Type: "+reply.type+
                    "\r\nContent-Length: "+reply.body.length+"\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n").getBytes(StandardCharsets.ISO_8859_1));
            output.write(reply.body); output.flush();
            System.out.println(path+" "+reply.status+" "+(System.currentTimeMillis()-started)+"ms");
        } catch (Exception error) { System.err.println("bridge request: "+error.getClass().getSimpleName()); }
    }

    private Reply route(String method, String path, Map<String,String> query, String body) throws Exception {
        if (path.equals("/api/status") && method.equals("GET")) return json(obj("version", "local-1.2", "passwordRequired", false,
                "verified", true, "defaultSources", defaults, "defaultLiveSources", new JSONArray(), "defaultSubscriptions", new JSONArray(),
                "mode", "on-device-compatibility"));
        if (path.equals("/api/auth") && method.equals("POST")) return json(obj("success", true));
        if (path.equals("/api/search") && method.equals("POST")) return json(search(new JSONObject(body)));
        if (path.equals("/api/detail") && method.equals("GET")) return json(detail(query));
        if (path.equals("/api/douban") && method.equals("GET")) return json(recommend(query));
        if (path.equals("/api/source/test") && method.equals("POST")) {
            String url = new JSONObject(body).getString("url");
            JSONObject root = fetchJson(add(url, "ac", "list"), false);
            return json(obj("ok", root.optJSONArray("list") != null, "count", root.optInt("total", 0), "status", 200));
        }
        if (path.equals("/api/source-list") && method.equals("GET")) {
            byte[] bytes = fetch(required(query,"url"), MAX_UPSTREAM, false);
            return new Reply(200, bytes, "application/json; charset=utf-8");
        }
        if (path.equals("/api/proxy") && method.equals("GET")) {
            byte[] bytes = fetch(required(query,"url"), 4*1024*1024, true);
            String type = bytes.length>3 && bytes[0]==(byte)0xff && bytes[1]==(byte)0xd8 ? "image/jpeg" :
                    bytes.length>8 && bytes[0]==(byte)0x89 && bytes[1]==0x50 ? "image/png" : "image/webp";
            return new Reply(200,bytes,type);
        }
        if (path.equals("/api/live/playlist") && method.equals("GET")) return json(playlist(required(query,"url")));
        return new Reply(404,"{\"error\":\"Unsupported endpoint\"}".getBytes(StandardCharsets.UTF_8),"application/json");
    }

    private JSONObject search(JSONObject request) throws Exception {
        String keyword = request.optString("wd", "").trim();
        if (keyword.isEmpty() || keyword.length()>160) throw new IOException("请输入要搜索的片名");
        JSONArray sources = request.optJSONArray("sources"); if (sources == null) sources = defaults;
        boolean filter = request.optBoolean("filterAdult", true);
        List<Future<JSONObject>> pending = new ArrayList<>();
        for (int i=0; i<Math.min(8,sources.length()); i++) {
            final JSONObject source = sources.optJSONObject(i);
            if (source == null || !source.optBoolean("enabled",true) || (filter && source.optBoolean("isAdult",false))) continue;
            pending.add(searches.submit(() -> {
                JSONArray items = new JSONArray();
                try {
                    String url = source.getString("url");
                    JSONObject result = fetchJson(add(url,"ac","detail","wd",keyword),false);
                    JSONArray list = result.optJSONArray("list");
                    if (list == null) throw new IOException("片源返回的格式不正确");
                    for (int n=0; n<list.length(); n++) {
                        JSONObject video=list.optJSONObject(n); if(video==null || (filter && adult(video))) continue;
                        items.put(obj("sourceName",source.optString("name","公开片源"),"sourceUrl",url,
                                "vodId",video.optString("vod_id"),"name",video.optString("vod_name"),
                                "pic",video.optString("vod_pic"),"typeName",video.optString("type_name"),
                                "year",video.optString("vod_year"),"area",video.optString("vod_area"),
                                "remarks",video.optString("vod_remarks"),"isAdult",false));
                    }
                    return obj("list",items);
                } catch(Exception error) { return obj("error",source.optString("name","片源")+"连接失败"); }
            }));
        }
        JSONArray items=new JSONArray(),failures=new JSONArray();
        for (Future<JSONObject> future:pending) {
            try {
                JSONObject result=future.get(15,TimeUnit.SECONDS);
                if(result.has("error")) failures.put(result.getString("error"));
                else { JSONArray list=result.getJSONArray("list");for(int i=0;i<list.length();i++) items.put(list.get(i)); }
            } catch(Exception error) { future.cancel(true); failures.put("片源请求超时"); }
        }
        return obj("list",items,"failures",failures);
    }

    private JSONObject detail(Map<String,String> query) throws Exception {
        JSONObject source=new JSONObject(required(query,"source"));
        JSONObject root=fetchJson(add(source.getString("url"),"ac","detail","ids",required(query,"id")),false);
        JSONArray list=root.optJSONArray("list");
        if(list==null || list.length()==0) throw new IOException("片源没有返回该影片详情");
        JSONObject video=list.getJSONObject(0);
        String[] groups=video.optString("vod_play_url","").split("\\$\\$\\$");
        String[] names=video.optString("vod_play_from","").split("\\$\\$\\$");
        int selected=0;
        for(int i=0;i<names.length && i<groups.length;i++) if(names[i].toLowerCase(Locale.ROOT).contains("m3u8")){selected=i;break;}
        JSONArray episodes=new JSONArray();
        if(groups.length>0) for(String item:groups[selected].split("#")) {
            int dollar=item.indexOf('$');String url=(dollar>=0?item.substring(dollar+1):item).trim();
            if(url.startsWith("https://") || url.startsWith("http://")) episodes.put(url);
        }
        if(episodes.length()==0) throw new IOException("没有可直接播放的地址");
        JSONObject info=obj("title",video.optString("vod_name"),"cover",video.optString("vod_pic"),
                "desc",video.optString("vod_content").replaceAll("<[^>]*>"," ").trim(),
                "remarks",video.optString("vod_remarks"),"year",video.optString("vod_year"),
                "area",video.optString("vod_area"),"actor",video.optString("vod_actor"));
        return obj("episodes",episodes,"videoInfo",info);
    }

    private JSONObject recommend(Map<String,String> query) throws Exception {
        String type=query.getOrDefault("type","movie"),tag=query.getOrDefault("tag","热门");
        int start=number(query.get("pageStart"),0,0,3000),size=number(query.get("pageSize"),48,1,60);
        try {
            JSONObject upstream=fetchJson(add("https://movie.douban.com/j/search_subjects", "type",type,
                    "tag",tag,"page_limit",String.valueOf(size),"page_start",String.valueOf(start)),true);
            JSONArray subjects=upstream.optJSONArray("subjects"),items=new JSONArray();
            if(subjects!=null && subjects.length()>0) {
                for(int i=0;i<subjects.length();i++) {
                    JSONObject item=subjects.optJSONObject(i);if(item!=null)items.put(obj("title",item.optString("title"),
                            "cover",item.optString("cover"),"rating",item.optString("rate")));
                }
                return obj("items",items,"recommendationSource","douban");
            }
        } catch(Exception unavailable) { System.err.println("Recommendation API unavailable; using configured public source"); }
        if(defaults.length()==0) return obj("items",new JSONArray(),"recommendationSource","unavailable");
        String source=defaults.getJSONObject(0).getString("url");
        JSONObject types=fetchJson(source,true);
        JSONArray classes=types.optJSONArray("class");
        String category="";
        String wanted=tag.contains("综艺")?"综艺":type.equals("movie")?"电影":"电视剧";
        if(classes!=null) for(int i=0;i<classes.length();i++) {
            JSONObject item=classes.optJSONObject(i);
            if(item!=null && wanted.equals(item.optString("type_name"))){category=item.optString("type_id");break;}
        }
        JSONArray items=new JSONArray();
        int perPage=20,first=start/perPage+1,skip=start%perPage;
        for(int pg=first;pg<first+4 && items.length()<size;pg++) {
            String url=category.isEmpty()?add(source,"ac","detail","pg",String.valueOf(pg)):
                    add(source,"ac","detail","pg",String.valueOf(pg),"t",category);
            JSONArray list=fetchJson(url,true).optJSONArray("list");
            if(list==null || list.length()==0) break;
            for(int i=(pg==first?skip:0);i<list.length() && items.length()<size;i++) {
                JSONObject video=list.optJSONObject(i);if(video==null || adult(video)) continue;
                String genre=video.optString("type_name");
                if(category.isEmpty()) {
                    if(wanted.equals("电影") && (genre.contains("剧") || genre.contains("综艺") || genre.contains("动漫"))) continue;
                    if(wanted.equals("电视剧") && !genre.contains("剧")) continue;
                    if(wanted.equals("综艺") && !genre.contains("综艺")) continue;
                }
                String rating=video.optString("vod_douban_score","");if(rating.equals("0.0") || rating.equals("0"))rating="";
                items.put(obj("title",video.optString("vod_name"),"cover",video.optString("vod_pic"),"rating",rating));
            }
        }
        return obj("items",items,"recommendationSource","configured-source-latest","label","片源最新内容");
    }

    private JSONObject playlist(String url) throws Exception {
        String text=new String(fetch(url,MAX_UPSTREAM,false),StandardCharsets.UTF_8);
        JSONArray channels=new JSONArray();String name="",group="",logo="";
        for(String line:text.split("\r?\n")) {
            line=line.trim();
            if(line.startsWith("#EXTINF:")) {
                int comma=line.lastIndexOf(',');name=comma>=0?line.substring(comma+1).trim():"频道";
                group=attribute(line,"group-title");logo=attribute(line,"tvg-logo");
            } else if(!line.isEmpty() && !line.startsWith("#") && (line.startsWith("https://") || line.startsWith("http://"))) {
                channels.put(obj("name",name.isEmpty()?"频道":name,"url",line,"group",group,"logo",logo));name="";
            }
        }
        return obj("channels",channels);
    }

    private static String attribute(String line,String key) {
        java.util.regex.Matcher m=java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(key)+"=\"([^\"]*)\"").matcher(line);
        return m.find()?m.group(1):"";
    }
    private static boolean adult(JSONObject o) {
        return o.optString("type_name").matches(".*(伦理|理论片|情色|福利|成人|裏番|里番).*") || o.optBoolean("isAdult",false);
    }
    private JSONObject fetchJson(String url,boolean cached) throws Exception {
        Cached old=cache.get(url);
        if(cached && old!=null && System.currentTimeMillis()-old.at<180000) return new JSONObject(old.text);
        String text=new String(fetch(url,3*1024*1024,false),StandardCharsets.UTF_8);
        JSONObject value=new JSONObject(text);
        if(cached && text.length()<700000) cache.put(url,new Cached(text));
        return value;
    }
    private static byte[] fetch(String target,int limit,boolean image) throws Exception {
        URL url=new URL(target);
        for(int redirects=0;redirects<5;redirects++) {
            if(!url.getProtocol().equals("https") && !url.getProtocol().equals("http")) throw new IOException("仅支持公开 HTTP/HTTPS 地址");
            if(url.getUserInfo()!=null) throw new IOException("地址不应包含认证信息");
            for(InetAddress address:InetAddress.getAllByName(url.getHost())) {
                byte[] bytes=address.getAddress();int first=bytes[0]&255,second=bytes[1]&255;
                if(address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress() || address.isSiteLocalAddress()
                        || address.isMulticastAddress() || (bytes.length==4 && (first==0 || first>=224 || (first==100 && second>=64 && second<=127)))
                        || (bytes.length==16 && (first&0xfe)==0xfc)) throw new IOException("仅允许公开网络地址");
            }
            HttpURLConnection connection=(HttpURLConnection)url.openConnection();
            connection.setConnectTimeout(5000);connection.setReadTimeout(8000);connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("User-Agent",UA);connection.setRequestProperty("Accept-Encoding","identity");
            if(image) connection.setRequestProperty("Referer",url.getHost().contains("douban")?"https://movie.douban.com/":url.getProtocol()+"://"+url.getHost()+"/");
            try {
                int code=connection.getResponseCode();
                if(code>=300 && code<400){String location=connection.getHeaderField("Location");if(location==null)throw new IOException("无效跳转");url=new URL(url,location);continue;}
                if(code<200 || code>=300) throw new IOException("公开片源请求失败 HTTP "+code);
                if(image && (connection.getContentType()==null || !connection.getContentType().toLowerCase(Locale.ROOT).startsWith("image/"))) throw new IOException("封面地址没有返回图片");
                try(InputStream input=connection.getInputStream();ByteArrayOutputStream output=new ByteArrayOutputStream()) {
                    byte[] buffer=new byte[8192];int n;
                    while((n=input.read(buffer))>=0){if(output.size()+n>limit)throw new IOException("响应内容过大");output.write(buffer,0,n);}
                    return output.toByteArray();
                }
            } finally { connection.disconnect(); }
        }
        throw new IOException("跳转次数过多");
    }
    private static Map<String,String> query(String raw) throws Exception {
        Map<String,String> result=new HashMap<>();if(raw==null)return result;
        for(String item:raw.split("&")){String[] pair=item.split("=",2);result.put(URLDecoder.decode(pair[0],"UTF-8"),pair.length>1?URLDecoder.decode(pair[1],"UTF-8"):"");}
        return result;
    }
    private static String add(String base,String... pairs) throws Exception {
        StringBuilder url=new StringBuilder(base);char join=base.contains("?")?'&':'?';
        for(int i=0;i<pairs.length;i+=2){url.append(join).append(URLEncoder.encode(pairs[i],"UTF-8")).append('=').append(URLEncoder.encode(pairs[i+1],"UTF-8"));join='&';}
        return url.toString();
    }
    private static String required(Map<String,String> query,String key) throws IOException {String v=query.get(key);if(v==null||v.isEmpty())throw new IOException("缺少参数 "+key);return v;}
    private static int number(String value,int fallback,int min,int max) {try{return Math.max(min,Math.min(max,Integer.parseInt(value)));}catch(Exception ignored){return fallback;}}
    private static JSONObject obj(Object... pairs) throws Exception {JSONObject value=new JSONObject();for(int i=0;i<pairs.length;i+=2)value.put((String)pairs[i],pairs[i+1]);return value;}
    private static Reply json(JSONObject value) {return new Reply(200,value.toString().getBytes(StandardCharsets.UTF_8),"application/json; charset=utf-8");}
    public synchronized void close() throws IOException {running=false;if(listener!=null)listener.close();clients.shutdownNow();searches.shutdownNow();cache.clear();}
    public static void main(String[] args) throws Exception {
        if(args.length!=2) throw new IllegalArgumentException("port config.json");
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        try(InputStream input=new FileInputStream(args[1])){byte[] b=new byte[4096];int n;while((n=input.read(b))>=0)bytes.write(b,0,n);}
        JSONObject config=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
        ApiServer server=new ApiServer(config.getJSONArray("sources"));server.start(Integer.parseInt(args[0]));
        Runtime.getRuntime().addShutdownHook(new Thread(()->{try{server.close();}catch(Exception ignored){}}));
    }
}
