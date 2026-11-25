/**
 * 蜕皮提醒详情：显示触发提醒的原图与关键信息，打开时自动标记已读。
 * 路由参数由日志屏的 AlertBanner 传入（避免额外按 id 查询接口）。
 * 纸感极简（P34）：照片直接铺开，信息用 1px 纸线分隔的键值行。
 * 按 P21 文案规则，不向用户显示置信度百分比。
 */
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { Divider, Eyebrow, Screen } from '@/components/ui';
import { useMarkAlertRead } from '@/hooks/useAlerts';
import { ensureToken, imageUrl } from '@/lib/auth';
import { formatDateCn } from '@/lib/dates';
import { colors, radius, space, type } from '@/lib/theme';

const STATE_LABEL: Record<string, string> = {
  shedding: '正在蜕皮',
  opaque: '蒙白期',
  normal: '状态正常',
  unknown: '状态待确认',
};

const KIND_LABEL: Record<string, { title: string; subtitle: string }> = {
  shedding_detected: { title: '蜕皮提醒', subtitle: '设备自动抓拍的蜕皮提醒' },
  device_silent: { title: '设备可能离线', subtitle: '长时间没有收到照片' },
  no_detection: { title: '看不到守宫', subtitle: '连续多张照片没拍到守宫' },
};

export default function AlertDetailScreen() {
  const params = useLocalSearchParams<{
    id: string;
    kind?: string;
    image_id?: string;
    state?: string;
    local_date?: string;
    confidence?: string;
  }>();
  const markRead = useMarkAlertRead();
  const done = useRef(false);
  const [tokenReady, setTokenReady] = useState(false);

  useEffect(() => {
    // 图片 URL 用 ?token= 鉴权，确保令牌就绪后再渲染图片。
    void ensureToken()
      .then(() => setTokenReady(true))
      .catch(() => setTokenReady(false));
  }, []);

  useEffect(() => {
    if (done.current || !params.id) return;
    done.current = true;
    markRead.mutate({ alertId: params.id, read: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const isShedding = !params.kind || params.kind === 'shedding_detected';
  const kindMeta = KIND_LABEL[params.kind ?? 'shedding_detected'];
  const label = isShedding
    ? params.state
      ? (STATE_LABEL[params.state] ?? '蜕皮提醒')
      : '蜕皮提醒'
    : (kindMeta?.title ?? '设备提醒');

  return (
    <Screen>
      <Text style={styles.kindTitle}>{kindMeta?.title ?? label}</Text>
      {kindMeta?.subtitle ? <Text style={styles.kindSubtitle}>{kindMeta.subtitle}</Text> : null}

      <Divider />

      {params.image_id && tokenReady ? (
        <Image
          source={{ uri: imageUrl(params.image_id) }}
          style={styles.image}
          resizeMode="contain"
        />
      ) : (
        <View style={styles.imageMissing}>
          <Text style={styles.missing}>
            {params.image_id ? '照片加载中…' : '这条提醒没有照片'}
          </Text>
        </View>
      )}

      <Divider />

      <View style={styles.metaRow}>
        <Text style={styles.metaKey}>日期</Text>
        <Text style={styles.metaValue}>
          {params.local_date ? formatDateCn(params.local_date) : '—'}
        </Text>
      </View>
      <View style={[styles.metaRow, styles.metaDivider]}>
        <Text style={styles.metaKey}>{isShedding ? '判定' : '类型'}</Text>
        <Text style={styles.metaValue}>{label}</Text>
      </View>

      <Eyebrow>说明</Eyebrow>
      <Text style={styles.note}>
        这是设备自动拍到的，不需要你做任何操作。看到发白的皮时，把水盆加满、保持湿润就好，别帮它撕。
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  kindTitle: {
    ...type.display,
    fontSize: 26,
    lineHeight: 34,
    color: colors.foreground,
  },
  kindSubtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  image: {
    width: '100%',
    height: 320,
    borderRadius: radius.sm,
    backgroundColor: colors.muted,
  },
  imageMissing: {
    height: 200,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    backgroundColor: colors.muted,
  },
  missing: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: space.md,
  },
  metaDivider: {
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  metaKey: { ...type.bodySm, color: colors.mutedForeground },
  metaValue: { ...type.bodySm, fontWeight: '700', color: colors.foreground },
  note: {
    ...type.bodySm,
    color: colors.body,
  },
});
