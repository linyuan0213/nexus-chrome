import { describe, expect, it } from 'vitest';

import {
  emptyProfile,
  FIELD_DEFS,
  FIELD_GROUPS,
  formToProfile,
  profileToForm,
} from '@/components/profiles/fingerprint-schema';

describe('fingerprint-schema', () => {
  it('schema 覆盖所有分组', () => {
    expect(FIELD_GROUPS).toContain('基础');
    expect(FIELD_GROUPS).toContain('WebGL');
    expect(FIELD_DEFS.length).toBeGreaterThan(20);
  });

  it('空画像可往返转换且字段类型正确', () => {
    const profile = emptyProfile();
    const form = profileToForm(profile);
    const back = formToProfile(form, { percent: 100, nodes: [] });
    expect(back.fingerprint.platform).toBe('Linux x86_64');
    expect(back.fingerprint.cores).toBe(8);
    expect(back.fingerprint.languages).toEqual(['zh-CN', 'zh']);
    expect(back.fingerprint.webgl_params).toEqual({});
    expect(back.enabled).toBe(true);
  });

  it('JSON 字段解析：空字符串 → 空对象', () => {
    const form = profileToForm(emptyProfile());
    form.webgl_params = '';
    const back = formToProfile(form, { percent: 100, nodes: [] });
    expect(back.fingerprint.webgl_params).toEqual({});
  });

  it('JSON 字段解析：合法 JSON → 对象', () => {
    const form = profileToForm(emptyProfile());
    form.webgl_params = '{"MAX_TEXTURE_SIZE": 16384}';
    const back = formToProfile(form, { percent: 100, nodes: [] });
    expect(back.fingerprint.webgl_params).toEqual({ MAX_TEXTURE_SIZE: 16384 });
  });

  it('JSON 字段解析：非法 JSON 抛错', () => {
    const form = profileToForm(emptyProfile());
    form.webgl_params = '{bad json';
    expect(() => formToProfile(form, { percent: 100, nodes: [] })).toThrow();
  });

  it('tags 字段：viewport_dims 转数字', () => {
    const form = profileToForm(emptyProfile());
    form.webgl_viewport_dims = ['1920', '1080'];
    const back = formToProfile(form, { percent: 100, nodes: [] });
    expect(back.fingerprint.webgl_viewport_dims).toEqual([1920, 1080]);
  });

  it('battery_level 空值保持 null', () => {
    const form = profileToForm(emptyProfile());
    form.battery_level = null;
    const back = formToProfile(form, { percent: 100, nodes: [] });
    expect(back.fingerprint.battery_level).toBeNull();
  });

  it('profileToForm 保留 profile_id/name/version 之外信息', () => {
    const profile = emptyProfile();
    profile.profile_id = 'mac_work';
    profile.name = '测试画像';
    profile.fingerprint.ua = 'Mozilla/5.0 Test';
    const form = profileToForm(profile);
    expect(form.profile_id).toBe('mac_work');
    expect(form.name).toBe('测试画像');
    expect(form.ua).toBe('Mozilla/5.0 Test');
  });
});
