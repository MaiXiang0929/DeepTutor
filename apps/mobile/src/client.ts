import { requestJson, websocketUrl } from "@deeptutor/shared-protocol";

export const post = (value: unknown): RequestInit => ({
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify(value),
});

export function serverOrigin(value: string): string {
  const url = new URL(value.trim());
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("请输入有效的 HTTP(S) 服务地址");
  }
  return url.origin;
}

export class TutorClient {
  readonly origin: string;

  constructor(origin: string) {
    this.origin = origin;
  }

  json<T>(path: string, init?: RequestInit) {
    return requestJson<T>(this.origin, path, init);
  }

  async isAuthenticated(): Promise<boolean> {
    const status = await this.json<{enabled: boolean; authenticated: boolean} | null>(
      "/api/auth/status",
    );
    if (typeof status?.enabled !== "boolean" || typeof status.authenticated !== "boolean") {
      throw new Error("请填写 DeepTutor 后端地址，Metro 地址只用于加载应用");
    }
    return status.authenticated;
  }

  fetch(path: string, init?: RequestInit) {
    return fetch(new URL(path, this.origin), {credentials: "include", ...init});
  }

  socket(path: string) {
    return new WebSocket(websocketUrl(this.origin, path));
  }
}
