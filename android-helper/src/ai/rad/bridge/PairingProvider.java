package ai.rad.bridge;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;

/** Only the local Android shell can retrieve the per-install bridge credential. */
public class PairingProvider extends ContentProvider {
  @Override public boolean onCreate(){return true;}
  @Override public Bundle call(String method,String arg,Bundle extras){
    if(Binder.getCallingUid()!=2000 && Binder.getCallingUid()!=0)throw new SecurityException("Local ADB shell required");
    if(!"token".equals(method))throw new IllegalArgumentException("Unknown pairing method");
    try {Bundle result=new Bundle();result.putString("token",BridgeServer.token(getContext()));return result;}
    catch(Exception error){throw new IllegalStateException("Local pairing unavailable",error);}
  }
  @Override public Cursor query(Uri u,String[] p,String s,String[] a,String order){throw new UnsupportedOperationException();}
  @Override public String getType(Uri u){return null;}
  @Override public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
  @Override public int delete(Uri u,String s,String[] a){throw new UnsupportedOperationException();}
  @Override public int update(Uri u,ContentValues v,String s,String[] a){throw new UnsupportedOperationException();}
}
