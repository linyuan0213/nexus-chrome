/** 指纹字段 schema：驱动 FingerprintFieldsEditor 渲染与 FpProfile 组装。 */

import type { FingerprintFields, FpProfile, RolloutRule } from '@/api/types';

export type FieldType = 'text' | 'number' | 'switch' | 'tags' | 'json' | 'select';

export interface FieldDef {
  key: keyof FingerprintFields;
  label: string;
  type: FieldType;
  group: string;
  hint?: string;
  options?: Array<{ label: string; value: number | string }>;
}

export const FIELD_DEFS: FieldDef[] = [
  // 基础
  { key: 'ua', label: 'User-Agent', type: 'text', group: '基础' },
  {
    key: 'ua_full_version',
    label: 'UA 完整版本',
    type: 'text',
    group: '基础',
    hint: '应与浏览器二进制版本一致',
  },
  { key: 'ua_brand_version', label: 'UA 品牌版本', type: 'text', group: '基础' },
  { key: 'platform', label: 'Platform', type: 'text', group: '基础', hint: '如 MacIntel / Linux x86_64' },
  { key: 'languages', label: '语言列表', type: 'tags', group: '基础' },
  { key: 'vendor', label: 'Vendor', type: 'text', group: '基础' },
  { key: 'app_version', label: 'appVersion', type: 'text', group: '基础' },
  { key: 'dnt', label: 'Do Not Track', type: 'switch', group: '基础' },
  // 硬件
  { key: 'cores', label: 'CPU 核数', type: 'number', group: '硬件', hint: '应与宿主机实际核数一致' },
  { key: 'memory', label: '内存 (GB)', type: 'number', group: '硬件' },
  { key: 'touch_points', label: '触摸点数 (-1=自动)', type: 'number', group: '硬件' },
  // UA-CH
  { key: 'uad_platform', label: 'UAD 平台', type: 'text', group: 'UA-CH' },
  { key: 'uad_platform_version', label: 'UAD 平台版本', type: 'text', group: 'UA-CH' },
  { key: 'uad_arch', label: 'UAD 架构', type: 'text', group: 'UA-CH' },
  { key: 'uad_model', label: 'UAD 型号', type: 'text', group: 'UA-CH' },
  // WebGL
  { key: 'webgl_vendor', label: 'WebGL Vendor', type: 'text', group: 'WebGL' },
  { key: 'webgl_renderer', label: 'WebGL Renderer', type: 'text', group: 'WebGL' },
  { key: 'gl_max_texture_size', label: '最大纹理 (0=自动)', type: 'number', group: 'WebGL' },
  {
    key: 'webgl_params',
    label: 'WebGL 参数 (JSON)',
    type: 'json',
    group: 'WebGL',
    hint: '留空由服务端按平台生成自洽值',
  },
  { key: 'webgl_viewport_dims', label: '视口尺寸', type: 'tags', group: 'WebGL' },
  { key: 'webgl_extensions_remove', label: '移除扩展', type: 'tags', group: 'WebGL' },
  // 屏幕
  {
    key: 'screen_width',
    label: '屏幕宽 (0=自动)',
    type: 'number',
    group: '屏幕',
    hint: '须与窗口/显示尺寸一致',
  },
  { key: 'screen_height', label: '屏幕高 (0=自动)', type: 'number', group: '屏幕' },
  { key: 'screen_color_depth', label: '色深 (0=自动)', type: 'number', group: '屏幕' },
  // 网络与区域
  {
    key: 'timezone',
    label: '时区',
    type: 'text',
    group: '网络与区域',
    hint: '如 Asia/Shanghai，应与出口 IP 一致',
  },
  { key: 'rtc_ip', label: 'WebRTC IP', type: 'text', group: '网络与区域' },
  { key: 'webrtc_replace_host_ip', label: 'WebRTC 替换主机 IP', type: 'switch', group: '网络与区域' },
  { key: 'net_rtt', label: '网络 RTT (ms)', type: 'number', group: '网络与区域' },
  { key: 'net_downlink', label: '下行带宽 (Mbps)', type: 'number', group: '网络与区域' },
  { key: 'net_downlink_max', label: '下行带宽上限', type: 'number', group: '网络与区域' },
  { key: 'net_effective_type', label: '网络类型', type: 'text', group: '网络与区域' },
  { key: 'online', label: 'onLine', type: 'text', group: '网络与区域' },
  // 噪声
  {
    key: 'canvas_noise',
    label: 'Canvas 噪声',
    type: 'switch',
    group: '噪声',
    hint: '开启会被 BrowserScan 标记，建议关闭',
  },
  { key: 'canvas_seed', label: 'Canvas 种子 (0=随机)', type: 'number', group: '噪声' },
  {
    key: 'audio_noise',
    label: 'Audio 噪声',
    type: 'switch',
    group: '噪声',
    hint: '开启会被 BrowserScan 标记，建议关闭',
  },
  { key: 'audio_rate', label: 'Audio 采样率 (0=默认)', type: 'number', group: '噪声' },
  { key: 'audio_seed', label: 'Audio 种子 (0=随机)', type: 'number', group: '噪声' },
  { key: 'font_block', label: '字体屏蔽列表', type: 'tags', group: '噪声' },
  // 电池与其他
  { key: 'battery_level', label: '电池电量 (留空=自动)', type: 'number', group: '电池与其他' },
  { key: 'battery_charging', label: '充电中 (留空=自动)', type: 'switch', group: '电池与其他' },
  {
    key: 'pdf_enabled',
    label: 'PDF 查看器',
    type: 'select',
    group: '电池与其他',
    options: [
      { label: '自动 (-1)', value: -1 },
      { label: '禁用 (0)', value: 0 },
      { label: '启用 (1)', value: 1 },
    ],
  },
];

export const FIELD_GROUPS = [...new Set(FIELD_DEFS.map((f) => f.group))];

export type FormValue = string | number | boolean | string[] | null;

export type ProfileFormModel = Record<string, FormValue> & {
  profile_id: string;
  name: string;
  enabled: boolean;
};

/** FingerprintFields → 表单模型（数组/对象转字符串便于编辑）。 */
export function profileToForm(profile: FpProfile): ProfileFormModel {
  const model: ProfileFormModel = {
    profile_id: profile.profile_id,
    name: profile.name,
    enabled: profile.enabled,
  };
  for (const def of FIELD_DEFS) {
    const v = profile.fingerprint[def.key];
    if (def.type === 'tags') {
      model[def.key] = Array.isArray(v) ? v.map(String) : [];
    } else if (def.type === 'json') {
      model[def.key] = v && Object.keys(v).length ? JSON.stringify(v, null, 2) : '';
    } else if (def.type === 'number' && (v === null || v === undefined)) {
      model[def.key] = null;
    } else if (def.type === 'switch' && (v === null || v === undefined)) {
      model[def.key] = false;
    } else {
      model[def.key] = v as FormValue;
    }
  }
  return model;
}

/** 表单模型 → FpProfile 提交体。 */
export function formToProfile(model: ProfileFormModel, rollout: RolloutRule, version = 1): FpProfile {
  const fingerprint = {} as FingerprintFields;
  for (const def of FIELD_DEFS) {
    const raw = model[def.key];
    if (def.type === 'tags') {
      const arr = Array.isArray(raw) ? raw : [];
      (fingerprint as unknown as Record<string, unknown>)[def.key] =
        def.key === 'webgl_viewport_dims' ? arr.map(Number).filter((n) => !Number.isNaN(n)) : arr;
    } else if (def.type === 'json') {
      const s = String(raw ?? '').trim();
      (fingerprint as unknown as Record<string, unknown>)[def.key] = s
        ? (JSON.parse(s) as Record<string, number>)
        : {};
    } else if (def.key === 'battery_level') {
      (fingerprint as unknown as Record<string, unknown>)[def.key] =
        raw === null || raw === '' ? null : Number(raw);
    } else if (def.key === 'battery_charging') {
      (fingerprint as unknown as Record<string, unknown>)[def.key] = raw ? true : null;
    } else if (def.type === 'number') {
      (fingerprint as unknown as Record<string, unknown>)[def.key] =
        raw === null || raw === '' ? 0 : Number(raw);
    } else if (def.type === 'select') {
      (fingerprint as unknown as Record<string, unknown>)[def.key] = Number(raw);
    } else if (def.type === 'switch') {
      (fingerprint as unknown as Record<string, unknown>)[def.key] = Boolean(raw);
    } else {
      (fingerprint as unknown as Record<string, unknown>)[def.key] = String(raw ?? '');
    }
  }
  return {
    profile_id: model.profile_id,
    name: model.name,
    version,
    enabled: model.enabled,
    rollout,
    fingerprint,
  };
}

/** 生成空白画像（与后端 FingerprintFields 默认值对齐）。 */
export function emptyProfile(): FpProfile {
  const fingerprint = {} as FingerprintFields;
  for (const def of FIELD_DEFS) {
    switch (def.type) {
      case 'tags':
        (fingerprint as unknown as Record<string, unknown>)[def.key] =
          def.key === 'languages' ? ['zh-CN', 'zh'] : [];
        break;
      case 'json':
        (fingerprint as unknown as Record<string, unknown>)[def.key] = {};
        break;
      case 'number':
        (fingerprint as unknown as Record<string, unknown>)[def.key] =
          def.key === 'cores'
            ? 8
            : def.key === 'memory'
              ? 8
              : def.key === 'pdf_enabled' || def.key === 'touch_points'
                ? def.key === 'pdf_enabled'
                  ? -1
                  : -1
                : 0;
        break;
      case 'select':
        (fingerprint as unknown as Record<string, unknown>)[def.key] = -1;
        break;
      case 'switch':
        (fingerprint as unknown as Record<string, unknown>)[def.key] = def.key === 'webrtc_replace_host_ip';
        break;
      default:
        (fingerprint as unknown as Record<string, unknown>)[def.key] =
          def.key === 'platform'
            ? 'Linux x86_64'
            : def.key === 'uad_platform'
              ? 'Linux'
              : def.key === 'uad_arch'
                ? 'x86'
                : '';
    }
  }
  return {
    profile_id: '',
    name: '',
    version: 1,
    enabled: true,
    rollout: { percent: 100, nodes: [] },
    fingerprint,
  };
}
