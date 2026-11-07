package ai.rad.bridge;
import android.app.Notification;
import android.app.PendingIntent;
import android.os.Bundle;
import android.service.notification.*;
import org.json.*;
import java.util.*;

public class MessageNotifications extends NotificationListenerService {
  static volatile boolean connected=false;
  private static final Map<String,PendingIntent> intents=new LinkedHashMap<>();
  @Override public void onListenerConnected(){connected=true;for(StatusBarNotification n:getActiveNotifications())onNotificationPosted(n);}
  @Override public void onListenerDisconnected(){connected=false;}
  @Override public void onNotificationPosted(StatusBarNotification sbn){
    if(!ReaderService.allowed(sbn.getPackageName()))return;
    Notification n=sbn.getNotification();
    if((n.flags&Notification.FLAG_GROUP_SUMMARY)!=0)return;
    Bundle extras=n.extras;if(extras==null)return;
    try {
      String id=UUID.nameUUIDFromBytes(sbn.getKey().getBytes("UTF-8")).toString();
      String title=ReaderService.string(extras.getCharSequence(Notification.EXTRA_TITLE));
      String text=ReaderService.string(extras.getCharSequence(Notification.EXTRA_TEXT));
      boolean group=extras.getBoolean("android.isGroupConversation",false);
      synchronized(intents){if(n.contentIntent!=null)intents.put(id,n.contentIntent);while(intents.size()>100)intents.remove(intents.keySet().iterator().next());}
      BridgeServer.publish(new JSONObject().put("type","notification").put("id",id).put("package",sbn.getPackageName())
        .put("title",title).put("text",text).put("group",group).put("posted_at",sbn.getPostTime()));
    }catch(Exception error){BridgeServer.failure("notification.read",error);android.util.Log.e("RadBridge","Notification read failed",error);}
  }
  static void open(String id)throws Exception {
    PendingIntent intent;synchronized(intents){intent=intents.get(id);}
    if(intent==null)throw new IllegalStateException("Notification is no longer available");
    intent.send();
  }
  @Override public void onNotificationRemoved(StatusBarNotification sbn){
    String id=UUID.nameUUIDFromBytes(sbn.getKey().getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
    synchronized(intents){intents.remove(id);}
  }
}
