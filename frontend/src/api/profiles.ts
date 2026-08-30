/** /api/profiles 指纹画像 API（管理端，需 FP_ADMIN_TOKEN 时带 query 鉴权）。 */

import { get, post } from './client';
import type { FpProfile, NodeProfileData, ProfileSummary, RolloutRule, VersionsData } from './types';

export function listProfiles(): Promise<{ profiles: ProfileSummary[] }> {
  return get('/api/profiles');
}

/** 拉取完整画像（含指纹字段）。注意：后端该接口校验 FP_NODE_TOKEN。 */
export function getProfile(profileId: string): Promise<NodeProfileData> {
  return get(`/api/profiles/${encodeURIComponent(profileId)}`);
}

export function saveProfile(profile: FpProfile): Promise<unknown> {
  return post('/api/profiles', profile);
}

export function getVersions(profileId: string): Promise<VersionsData> {
  return get(`/api/profiles/${encodeURIComponent(profileId)}/versions`);
}

export function rollbackProfile(profileId: string, toVersion: number): Promise<unknown> {
  return post(`/api/profiles/${encodeURIComponent(profileId)}/rollback`, undefined, {
    to_version: toVersion,
  });
}

export function grayPublish(profileId: string, rollout: RolloutRule): Promise<unknown> {
  return post(`/api/profiles/${encodeURIComponent(profileId)}/gray`, rollout);
}
