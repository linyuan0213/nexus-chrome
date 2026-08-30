/** /instances 与 /status API（原始响应，非 ApiResponse 包装）。 */

import { getRaw, del, post } from './client';
import type { InstanceInfo, StatusData } from './types';

export function getStatus(): Promise<StatusData> {
  return getRaw('/status');
}

export function listInstances(): Promise<{ instances: InstanceInfo[] }> {
  return getRaw('/instances');
}

/** 关闭实例；默认实例后端返回 code=1（由 client 解包为 ApiError）。 */
export async function closeInstance(key: string): Promise<null> {
  return del(`/instances/${encodeURIComponent(key)}`);
}

/** 拉起已停止的实例（后端沿用创建时的指纹环境重启 Chrome）。 */
export async function restartInstance(key: string): Promise<null> {
  return post(`/instances/${encodeURIComponent(key)}/restart`);
}
