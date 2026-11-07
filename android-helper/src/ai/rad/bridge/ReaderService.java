package ai.rad.bridge;
import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.*;
import android.graphics.Rect;
import org.json.*;
import java.util.concurrent.*;

public class ReaderService extends AccessibilityService {
  static volatile ReaderService instance;
  final ScheduledExecutorService reader=Executors.newSingleThreadScheduledExecutor();
  private ScheduledFuture<?> pending;
  private BridgeServer server;
  private String last="";
  static boolean allowed(String pkg) {return "io.anonchat".equals(pkg)||"org.vidogram.messenger".equals(pkg)||"org.telegram.messenger".equals(pkg);}
  @Override public void onServiceConnected() {
    instance=this;
    try {server=new BridgeServer(this);server.start();} catch(Exception e) {android.util.Log.e("RadBridge","Bridge startup failed",e);}
    schedule();
  }
  @Override public void onAccessibilityEvent(AccessibilityEvent event) {schedule();}
  private synchronized void schedule() {
    // Coalesce bursts without postponing indefinitely under continuous events.
    if(pending==null||pending.isDone()) pending=reader.schedule(()->{
      try {capture();}catch(Exception e){BridgeServer.failure("accessibility.capture",e);android.util.Log.e("RadBridge","Accessibility capture failed",e);}
    },60,TimeUnit.MILLISECONDS);
  }
  JSONObject fresh() throws Exception {return reader.submit(()->capture()).get(6,TimeUnit.SECONDS);}
  JSONObject capture() throws Exception {
    AccessibilityNodeInfo root=getRootInActiveWindow();
    if(root==null)return new JSONObject().put("available",false);
    try {
      root.refresh();String pkg=String.valueOf(root.getPackageName());
      if(!allowed(pkg))return new JSONObject().put("available",false);
      JSONObject tree=node(root,0,new int[]{0});String serialized=tree.toString();
      if(!serialized.equals(last)){last=serialized;BridgeServer.publish(new JSONObject().put("type","snapshot").put("package",pkg));}
      return new JSONObject().put("available",true).put("package",pkg).put("tree",tree)
        .put("captured_at",System.currentTimeMillis()).put("revision",BridgeServer.revision());
    } finally {root.recycle();}
  }
  private JSONObject node(AccessibilityNodeInfo n,int depth,int[] count)throws Exception {
    if(depth>40||++count[0]>6000)throw new IllegalStateException("Accessibility tree exceeds limits");
    n.refresh(); // Invalidate stale child/text caches after React Native transitions.
    Rect r=new Rect();n.getBoundsInScreen(r);
    JSONObject a=new JSONObject();
    a.put("package",string(n.getPackageName())).put("class",string(n.getClassName()))
     .put("text",n.isPassword()?"":string(n.getText())).put("content-desc",n.isPassword()?"":string(n.getContentDescription()))
     .put("resource-id",string(n.getViewIdResourceName())).put("bounds","["+r.left+","+r.top+"]["+r.right+","+r.bottom+"]")
     .put("clickable",String.valueOf(n.isClickable())).put("long-clickable",String.valueOf(n.isLongClickable()))
     .put("scrollable",String.valueOf(n.isScrollable())).put("enabled",String.valueOf(n.isEnabled()))
     .put("focused",String.valueOf(n.isFocused())).put("visible-to-user",String.valueOf(n.isVisibleToUser()));
    JSONArray children=new JSONArray();
    for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null){try{children.put(node(c,depth+1,count));}finally{c.recycle();}}}
    return new JSONObject().put("attributes",a).put("children",children);
  }
  JSONObject editDraft(JSONObject request)throws Exception {
    java.util.concurrent.FutureTask<JSONObject> task=new java.util.concurrent.FutureTask<>(()->editNow(request));
    android.os.Handler main=new android.os.Handler(getMainLooper());main.post(task);
    try{return task.get(4,TimeUnit.SECONDS);}
    finally{if(!task.isDone()){task.cancel(false);main.removeCallbacks(task);}}
  }
  private JSONObject editNow(JSONObject request)throws Exception {
    String pkg=request.getString("package"),before=request.getString("before"),after=request.getString("after");
    if(!allowed(pkg)||after.length()>1500||before.length()>1500)throw new IllegalArgumentException("Unsupported draft");
    AccessibilityNodeInfo root=getRootInActiveWindow();
    if(root==null)return new JSONObject().put("changed",false);
    java.util.ArrayList<AccessibilityNodeInfo> editors=new java.util.ArrayList<>();
    boolean[] header={false};
    try{
      root.refresh();
      if(!pkg.equals(string(root.getPackageName())))return new JSONObject().put("changed",false);
      collectEditor(root,request,editors,header,0);
      if(editors.size()!=1||!header[0])return new JSONObject().put("changed",false);
      AccessibilityNodeInfo editor=editors.get(0);editor.refresh();
      String current=string(editor.getText());
      // Hint-only empty fields may expose their placeholder as text.
      if(editor.isShowingHintText())current="";
      if(!before.equals(current))return new JSONObject().put("changed",false);
      android.os.Bundle args=new android.os.Bundle();
      args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,after);
      editor.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
      boolean changed=editor.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args);
      return new JSONObject().put("changed",changed);
    }finally{for(AccessibilityNodeInfo editor:editors)editor.recycle();root.recycle();}
  }
  private void collectEditor(AccessibilityNodeInfo n,JSONObject request,java.util.List<AccessibilityNodeInfo> editors,boolean[] header,int depth)throws Exception {
    if(depth>40)return;n.refresh();if(!n.isVisibleToUser())return;
    Rect r=new Rect();n.getBoundsInScreen(r);String bounds="["+r.left+","+r.top+"]["+r.right+","+r.bottom+"]";
    if(bounds.equals(request.getString("header_bounds"))&&string(n.getText()).equals(request.getString("header")))header[0]=true;
    if(n.isEditable()&&!n.isPassword()&&n.isEnabled()&&"android.widget.EditText".equals(string(n.getClassName())))editors.add(AccessibilityNodeInfo.obtain(n));
    for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo child=n.getChild(i);if(child!=null){try{collectEditor(child,request,editors,header,depth+1);}finally{child.recycle();}}}
  }
  static String string(CharSequence text){return text==null?"":text.toString();}
  @Override public void onInterrupt() {}
  @Override public void onDestroy(){instance=null;if(server!=null)server.close();reader.shutdownNow();super.onDestroy();}
}
