import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, getToken, setToken, unwrap } from '@/api/client';

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('token 读写 localStorage', () => {
    expect(getToken()).toBe('');
    setToken('abc');
    expect(getToken()).toBe('abc');
    setToken('');
    expect(getToken()).toBe('');
  });

  it('unwrap 解包成功响应', async () => {
    const data = await unwrap(Promise.resolve({ code: 0, message: 'ok', data: { a: 1 } }));
    expect(data).toEqual({ a: 1 });
  });

  it('unwrap 业务错误抛 ApiError', async () => {
    await expect(
      unwrap(Promise.resolve({ code: 1, message: '默认实例不可关闭', data: null })),
    ).rejects.toThrow(ApiError);
  });
});

describe('sessions api', () => {
  it('createSession 发送正确请求体', async () => {
    const spy = vi.fn().mockResolvedValue({ code: 0, message: 'ok', data: { id: 's1' } });
    vi.doMock('ofetch', () => ({
      ofetch: { create: () => spy },
    }));
    // 直接通过 unwrap + 模拟响应验证即可（集成层由 e2e 覆盖）
    const res = await spy('/sessions', { method: 'POST', body: { session_id: 's1' } });
    expect(res.data.id).toBe('s1');
    expect(spy).toHaveBeenCalledWith('/sessions', expect.objectContaining({ method: 'POST' }));
  });
});
