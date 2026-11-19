/**
 * 服务器地址的推断规则。
 *
 * 这里是纯函数：不碰 React Native、不碰浏览器全局，方便单独编译后用 node 验证。
 *
 * 优先级：
 *   1. 显式配置（EXPO_PUBLIC_SERVER_URL 或用户在设置页填过的地址）永远最高；
 *   2. Web 端打开时，页面由服务端自己托管（A 包把前端挂在同一个地址下），
 *      直接用当前页面地址，用户不用手填，也不会连错；
 *   3. 但开发时页面跑在 Metro / Expo 的开发服务器上，那个地址不是后端，必须排除，
 *      否则界面能开、所有接口都失败，用户会以为服务没起来。
 */

/** Expo / Metro 开发服务器常开的端口：页面挂在这些端口上时，origin 不是后端地址。 */
export const EXPO_DEV_PORTS = [
  '8081',
  '8082',
  '19000',
  '19001',
  '19002',
  '19006',
  '19007',
] as const;

export interface LocationLike {
  origin: string;
  port: string;
}

/**
 * 推断默认服务器地址；推断不出来时返回空串，交给设置页让用户自己填。
 */
export function inferServerUrl(
  configuredUrl: string,
  location: LocationLike | null,
): string {
  if (configuredUrl) return configuredUrl.trim();
  if (!location || !location.origin) return '';
  if (EXPO_DEV_PORTS.includes(location.port as (typeof EXPO_DEV_PORTS)[number])) {
    return '';
  }
  return location.origin.trim();
}
