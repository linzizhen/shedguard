/**
 * 后端 API 客户端。
 *
 * - 服务器地址来自 serverUrl 模块（设置页配置）。
 * - 错误契约与后端一致：`{"error": {"code", "message", "request_id"}}`。
 * - 204 无-body 响应（DELETE）返回 undefined。
 */
import { getServerUrl } from './serverUrl';

/** 后端统一错误体 */
interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string | null;
  };
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

/** 没有配置服务器地址 */
export const NO_SERVER = 'NO_SERVER';

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getServerUrl().replace(/\/+$/, '');
  if (!base) {
    throw new ApiError(NO_SERVER, '请先在「设置」里填写服务器地址', 0);
  }

  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        // JSON 字符串体才显式设 Content-Type；FormData（multipart）的边界必须由运行时生成
        ...(typeof init?.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接服务器，请检查地址与网络', 0);
  }

  if (!res.ok) {
    let code = 'HTTP_ERROR';
    let message = `请求失败（HTTP ${res.status}）`;
    try {
      const body = (await res.json()) as ApiErrorBody;
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
    } catch {
      // 保留默认消息
    }
    throw new ApiError(code, message, res.status);
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
