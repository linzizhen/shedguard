/**
 * 蜕皮提醒详情：显示触发提醒的原图与关键信息，打开时自动标记已读。
 * 路由参数由日志屏的 AlertBanner 传入（避免额外按 id 查询接口）。
 */
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { Card, PageHeader, Screen } from '@/components/ui';
import { useMarkAlertRead } from '@/hooks/useAlerts';
import { useServerUrl } from '@/lib/serverUrl';
import { formatDateCn } from '@/lib/dates';
import { colors, radius } from '@/lib/theme';

const STATE_LABEL: Record<string, string> = {
  shedding: '正在蜕皮',
  opaque: '蒙白期',
  normal: '状态正常',
  unknown: '状态待确认',
};

export default function AlertDetailScreen() {
  const serverUrl = useServerUrl();
  const params = useLocalSearchParams<{
    id: string;
    image_id?: string;
    state?: string;
    local_date?: string;
    confidence?: string;
  }>();
  const markRead = useMarkAlertRead();
  const done = useRef(false);

  useEffect(() => {
    if (done.current || !params.id) return;
    done.current = true;
    markRead.mutate({ alertId: params.id, read: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const confidence = params.confidence ? Number(params.confidence) : null;
  const label = params.state ? (STATE_LABEL[params.state] ?? '蜕皮提醒') : '蜕皮提醒';

  return (
    <Screen>
      <PageHeader title={label} subtitle="设备自动抓拍的蜕皮提醒" />
      <Card style={styles.imageCard}>
        {params.image_id ? (
          <Image
            source={{ uri: `${serverUrl}/api/v1/images/${params.image_id}` }}
            style={styles.image}
            resizeMode="contain"
          />
        ) : (
          <Text style={styles.missing}>没有可显示的照片</Text>
        )}
      </Card>
      <Card style={styles.metaCard}>
        <View style={styles.metaRow}>
          <Text style={styles.metaKey}>日期</Text>
          <Text style={styles.metaValue}>
            {params.local_date ? formatDateCn(params.local_date) : '—'}
          </Text>
        </View>
        <View style={styles.metaRow}>
          <Text style={styles.metaKey}>判定</Text>
          <Text style={styles.metaValue}>{label}</Text>
        </View>
        <View style={styles.metaRow}>
          <Text style={styles.metaKey}>置信度</Text>
          <Text style={styles.metaValue}>
            {confidence != null ? `${Math.round(confidence * 100)}%` : '—'}
          </Text>
        </View>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  imageCard: { padding: 8 },
  image: {
    width: '100%',
    height: 320,
    borderRadius: radius.md,
    backgroundColor: colors.muted,
  },
  missing: {
    textAlign: 'center',
    paddingVertical: 40,
    color: colors.mutedForeground,
  },
  metaCard: { gap: 10 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between' },
  metaKey: { fontSize: 14, color: colors.mutedForeground },
  metaValue: { fontSize: 14, fontWeight: '700', color: colors.foreground },
});
