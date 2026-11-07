package ai.rad.bridge;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.provider.Settings;
import android.widget.*;

public class MainActivity extends Activity {
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    try { BridgeServer.token(this); } catch(Exception e) { android.util.Log.e("RadBridge","Token initialization failed",e); }
    LinearLayout layout=new LinearLayout(this); layout.setOrientation(1); layout.setPadding(30,35,30,20);
    TextView text=new TextView(this);
    text.setText("Rad.ai Bridge 0.1.15\n\nReads AnonChat and Telegram/Vidogram for your local Rad.ai panel.\n\n1. Enable Rad.ai Bridge under Accessibility.\n2. Enable notification access to receive background message previews.\n3. Return to Rad.ai on your computer and connect.\n\nThese permissions are optional and must be enabled by you. No permission is changed automatically. Data is served only on emulator localhost through authenticated ADB forwarding. Other applications are excluded.");
    text.setTextSize(17);layout.addView(text);
    Button access=new Button(this);access.setText("Open accessibility settings");
    access.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));layout.addView(access);
    Button notifications=new Button(this);notifications.setText("Open notification access settings");
    notifications.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));layout.addView(notifications);
    setContentView(layout);
  }
}
