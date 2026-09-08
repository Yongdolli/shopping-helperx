/** 웹푸시 구독 도우미. VAPID 공개키가 없으면(데모) 로컬 알림만 쓴다. */
import { api, VAPID_PUBLIC_KEY } from "./api";

export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function urlBase64ToUint8Array(b64: string): ArrayBuffer {
  const padding = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr.buffer;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

/** 권한 요청 → 구독 → 서버 저장. VAPID 키 없으면 권한만 받고 테스트 알림을 띄운다. */
export async function enablePush(): Promise<"subscribed" | "local-only" | "denied" | "unsupported"> {
  if (!pushSupported()) return "unsupported";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return "denied";
  const reg = await navigator.serviceWorker.ready;
  if (!VAPID_PUBLIC_KEY) {
    await reg.showNotification("Shopping Helper", { body: "알림이 켜졌습니다. (VAPID 키를 넣으면 서버 푸시도 옵니다)", icon: "/icon-192.png" });
    return "local-only";
  }
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY) });
  const json = sub.toJSON();
  await api.savePushSubscription({ endpoint: json.endpoint!, keys: { p256dh: json.keys!.p256dh, auth: json.keys!.auth } });
  await reg.showNotification("Shopping Helper", { body: "웹푸시가 연결되었습니다.", icon: "/icon-192.png" });
  return "subscribed";
}

export async function disablePush(): Promise<void> {
  const sub = await currentSubscription();
  if (sub) { await api.removePushSubscription(sub.endpoint); await sub.unsubscribe(); }
}
