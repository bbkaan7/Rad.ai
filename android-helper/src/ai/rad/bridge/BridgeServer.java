package ai.rad.bridge;
import android.content.Context;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.*;

class BridgeServer {
  private final ServerSocket socket;
  private final String auth;
  private final ExecutorService clients=Executors.newFixedThreadPool(4);
  private volatile boolean running=true;
  private static long seq=0;
  private static final String session=UUID.randomUUID().toString();
  private static final ArrayDeque<JSONObject> events=new ArrayDeque<>();
  static synchronized long revision(){return seq;}
  static void failure(String stage,Throwable error){
    try {
      JSONArray frames=new JSONArray();
      for(StackTraceElement f:error.getStackTrace()){
        if(frames.length()>=20)break;
        frames.put(new JSONObject().put("file",String.valueOf(f.getFileName())).put("line",f.getLineNumber())
          .put("function",f.getClassName()+"."+f.getMethodName()));
      }
      publish(new JSONObject().put("type","bridge_error").put("stage",stage)
        .put("error_type",error.getClass().getName()).put("frames",frames));
    }catch(Exception ignored){}
  }
  static synchronized void publish(JSONObject event)throws JSONException {
    event.put("seq",++seq);events.add(event);while(events.size()>128)events.removeFirst();BridgeServer.class.notifyAll();
  }
  static synchronized String token(Context context)throws Exception {
    File file=new File(context.getFilesDir(),"bridge-token");
    if(!file.exists()){
      byte[] bytes=new byte[32];new SecureRandom().nextBytes(bytes);StringBuilder value=new StringBuilder();
      for(byte b:bytes)value.append(String.format("%02x",b&255));Files.write(file.toPath(),value.toString().getBytes(StandardCharsets.US_ASCII));
    }
    return new String(Files.readAllBytes(file.toPath()),StandardCharsets.US_ASCII).trim();
  }
  BridgeServer(Context context)throws Exception {
    auth=token(context);socket=new ServerSocket();socket.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),8765),8);
  }
  void start(){new Thread(()->{while(running){try{Socket client=socket.accept();clients.submit(()->serve(client));}catch(IOException e){if(running)android.util.Log.e("RadBridge","Local accept failed",e);}}},"RadLocalBridge").start();}
  void close(){running=false;try{socket.close();}catch(IOException ignored){}clients.shutdownNow();}
  private void serve(Socket client){
    try(Socket c=client){
      c.setSoTimeout(12000);BufferedReader input=new BufferedReader(new InputStreamReader(c.getInputStream(),StandardCharsets.UTF_8));
      String request=input.readLine();if(request==null||request.length()>2048)return;
      String authorization="";int length=0;for(int i=0;i<32;i++){String line=input.readLine();if(line==null||line.isEmpty())break;if(line.length()>2048)return;if(line.toLowerCase(Locale.ROOT).startsWith("authorization:"))authorization=line.substring(14).trim();if(line.toLowerCase(Locale.ROOT).startsWith("content-length:"))length=Integer.parseInt(line.substring(15).trim());}
      if(!java.security.MessageDigest.isEqual(("Bearer "+auth).getBytes(StandardCharsets.UTF_8),authorization.getBytes(StandardCharsets.UTF_8))){respond(c,403,new JSONObject().put("error","Unauthorized"));return;}
      String[] parts=request.split(" ");if(parts.length<2)return;URI uri=URI.create(parts[1]);String path=uri.getPath();
      Map<String,String> query=new HashMap<>();if(uri.getRawQuery()!=null)for(String pair:uri.getRawQuery().split("&")){String[] kv=pair.split("=",2);query.put(kv[0],kv.length>1?URLDecoder.decode(kv[1],"UTF-8"):"");}
      JSONObject result;
      if("/health".equals(path))result=new JSONObject().put("version","0.1.15").put("draft_edit",1).put("session",session).put("accessibility",ReaderService.instance!=null).put("notifications",MessageNotifications.connected);
      else if("/snapshot".equals(path))result=ReaderService.instance.fresh();
      else if("/events".equals(path)){
        long after=Long.parseLong(query.getOrDefault("after","0"));JSONArray batch=new JSONArray();
        synchronized(BridgeServer.class){if(seq<=after)BridgeServer.class.wait(8000);for(JSONObject event:events)if(event.getLong("seq")>after)batch.put(event);result=new JSONObject().put("session",session).put("events",batch).put("revision",seq);}
      }else if("/open-notification".equals(path)&&"POST".equals(parts[0])){
        MessageNotifications.open(query.getOrDefault("id",""));result=new JSONObject().put("opened",true);
      }else if("/draft".equals(path)&&"POST".equals(parts[0])){
        // The desktop sends ASCII JSON (Unicode is escaped), so character and byte counts match.
        if(length<2||length>32000)throw new IllegalArgumentException("Invalid draft request length");
        char[] body=new char[length];int read=0;
        while(read<length){int count=input.read(body,read,length-read);if(count<0)throw new EOFException();read+=count;}
        result=ReaderService.instance.editDraft(new JSONObject(new String(body)));
      }else {respond(c,404,new JSONObject().put("error","Unknown endpoint"));return;}
      respond(c,200,result);
    }catch(java.net.SocketException disconnected){ /* Client shutdown cancels long polling. */ }catch(Exception e){failure("http.request",e);android.util.Log.w("RadBridge","Local request failed: "+e.getClass().getSimpleName());}
  }
  private void respond(Socket socket,int status,JSONObject data)throws IOException {
    byte[] body=data.toString().getBytes(StandardCharsets.UTF_8);OutputStream out=socket.getOutputStream();
    out.write(("HTTP/1.1 "+status+" Response\r\nContent-Type: application/json\r\nContent-Length: "+body.length+"\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));out.write(body);out.flush();
  }
}
