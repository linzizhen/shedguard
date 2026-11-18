/**
 * 分享照片：用户自愿把手拍到的蜕皮照片贡献出来（默认关闭）。
 * 说明写成人话，技术细节（收件箱、令牌）不出现。
 */
import { useState } from 'react';
import { Alert, Image, Pressable, StyleSheet, Switch, Text, View } from 'react-native';

import { Card, EmptyState, PrimaryButton, Screen, SectionTitle } from '@/components/ui';
import {
  useContributionSettings,
  useContributions,
  useCreateContributionExport,
  useUpdateContributionSettings,
  useUploadContributionsNow,
  useWithdrawContribution,
} from '@/hooks/useContributions';
import { contributionUrl } from '@/lib/auth';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, hairline, radius, space, type } from '@/lib/theme';
import type { ContributionSample, ContributionStatus } from '@/lib/types';

const STATUS_LABEL: Record<ContributionStatus, string> = {
  pending: '等着发送',
  uploaded: '已经发出去了',
  failed: '这次没发成，稍后会再试',
  withdrawn: '已撤回',
};

function formatDay(iso: string): string {
  const [, month, day] = iso.split('-');
  return `${Number(month)}月${Number(day)}日`;
}

function SampleRow({
  sample,
  onWithdraw,
  busy,
}: {
  sample: ContributionSample;
  onWithdraw: (id: string) => void;
  busy: boolean;
}) {
  const withdrawn = sample.upload_status === 'withdrawn';
  return (
    <View style={styles.sampleRow}>
      {withdrawn ? (
        <View style={[styles.thumb, styles.thumbGone]}>
          <Text style={styles.thumbGoneText}>已删</Text>
        </View>
      ) : (
        <Image source={{ uri: contributionUrl(sample.id) }} style={styles.thumb} />
      )}
      <View style={styles.sampleText}>
        <Text style={styles.sampleTitle}>{formatDay(sample.local_date)}</Text>
        <Text style={styles.sampleHint}>{STATUS_LABEL[sample.upload_status]}</Text>
      </View>
      {withdrawn ? null : (
        <Pressable
          onPress={() => onWithdraw(sample.id)}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="撤回这一张"
          style={({ pressed }) => [styles.withdraw, pressed && styles.pressed]}
        >
          <Text style={styles.withdrawText}>撤回</Text>
        </Pressable>
      )}
    </View>
  );
}

export default function ContributionScreen() {
  const serverUrl = useServerUrl();
  const settingsQuery = useContributionSettings();
  const listQuery = useContributions();
  const updateSettings = useUpdateContributionSettings();
  const withdraw = useWithdrawContribution();
  const uploadNow = useUploadContributionsNow();
  const createExport = useCreateContributionExport();
  const [notice, setNotice] = useState<string | null>(null);

  if (serverUrl === '') {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline-outline"
            title="App 还没连上电脑"
            subtitle="先回到「我的」，填好地址。"
          />
        </Card>
      </Screen>
    );
  }

  const setting = settingsQuery.data ?? null;
  const enabled = setting?.enabled ?? false;
  const includeFull = setting?.include_full ?? false;
  const stats = listQuery.data?.stats ?? null;
  const samples = listQuery.data?.items ?? [];

  function confirmWithdraw(sampleId: string) {
    Alert.alert('不再分享这一张？', '会从这台电脑和我们的收件箱里一起删掉。', [
      { text: '算了', style: 'cancel' },
      {
        text: '删掉',
        style: 'destructive',
        onPress: () => withdraw.mutate(sampleId),
      },
    ]);
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>
        你愿意的话，设备拍到的蜕皮照片也能帮到别的守宫。默认是关着的，随时可以停。
      </Text>

      {setting === null ? (
        <Card>
          <EmptyState icon="hourglass-outline" title="正在读取…" />
        </Card>
      ) : (
        <Card style={{ gap: space.md }}>
          <View style={styles.row}>
            <Text style={styles.rowLabel}>允许分享</Text>
            <Switch
              value={enabled}
              onValueChange={(next) =>
                updateSettings.mutate({ enabled: next, include_full: includeFull })
              }
              trackColor={{ true: colors.primary, false: colors.border }}
              thumbColor={colors.card}
            />
          </View>
          <Text style={styles.hint}>
            只发裁剪后的特写，不带宠物名字、不带设备号，也不带原始文件信息。
          </Text>

          <View style={styles.row}>
            <Text style={[styles.rowLabel, !enabled && styles.rowDisabled]}>
              连整张原图一起发
            </Text>
            <Switch
              value={includeFull}
              disabled={!enabled}
              onValueChange={(next) =>
                updateSettings.mutate({ enabled: true, include_full: next })
              }
              trackColor={{ true: colors.primary, false: colors.border }}
              thumbColor={colors.card}
            />
          </View>
          <Text style={styles.hint}>
            不打开也没关系，只发特写就够我们用了。整张原图会多带上环境画面。
          </Text>
        </Card>
      )}

      {stats ? (
        <>
          <SectionTitle>分享情况</SectionTitle>
          <Card style={{ gap: space.sm }}>
            <Text style={styles.stat}>
              已经分享 {stats.uploaded} 张 · 还有 {stats.pending} 张等着发送
            </Text>
            {stats.failed > 0 ? (
              <Text style={styles.hint}>{stats.failed} 张没发出去，我们会自己再试。</Text>
            ) : null}
            {stats.withdrawn > 0 ? (
              <Text style={styles.hint}>已经撤回 {stats.withdrawn} 张。</Text>
            ) : null}
            <Text style={styles.hint}>一次蜕皮最多留 3 张，不会拍到停不下来。</Text>
          </Card>

          <PrimaryButton
            title={uploadNow.isPending ? '发送中…' : '立即发送'}
            onPress={() =>
              uploadNow.mutate(undefined, {
                onSuccess: (summary) => {
                  setNotice(
                    summary.skipped > 0
                      ? '这台设备还没配置收件箱，照片先留在你的电脑上。'
                      : `发出去 ${summary.uploaded} 张。`,
                  );
                },
              })
            }
            disabled={uploadNow.isPending || stats.pending === 0}
          />

          <PrimaryButton
            title={createExport.isPending ? '打包中…' : '打包成压缩包'}
            onPress={() =>
              createExport.mutate(undefined, {
                onSuccess: (exported) =>
                  setNotice(`打好了：${exported.filename}（${exported.sample_count} 张）`),
              })
            }
            disabled={createExport.isPending || stats.total === 0}
          />

          {createExport.isError ? (
            <Text style={styles.errorText}>还没有可以打包的照片。</Text>
          ) : null}
          {notice ? <Text style={styles.notice}>{notice}</Text> : null}
        </>
      ) : null}

      <SectionTitle>分享过的照片</SectionTitle>
      {samples.length === 0 ? (
        <Card>
          <EmptyState
            icon="images-outline"
            title="还没有分享过"
            subtitle="打开上面的开关，之后拍到的蜕皮照片就会出现在这里。"
          />
        </Card>
      ) : (
        <Card style={{ gap: space.sm + 2 }}>
          {samples.map((sample) => (
            <SampleRow
              key={sample.id}
              sample={sample}
              busy={withdraw.isPending}
              onWithdraw={confirmWithdraw}
            />
          ))}
        </Card>
      )}

      <Text style={styles.hint}>
        撤回会把这张从我们这边也删掉。关掉开关之后，新照片不会再上传。
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: { ...type.bodySm, color: colors.mutedForeground },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    minHeight: 44,
  },
  rowLabel: { ...type.body, fontWeight: '700', color: colors.foreground },
  rowDisabled: { color: colors.faintForeground },
  stat: { ...type.body, fontWeight: '700', color: colors.foreground },
  sampleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 56,
  },
  thumb: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    backgroundColor: colors.muted,
  },
  thumbGone: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: hairline,
    borderColor: colors.border,
  },
  thumbGoneText: { ...type.caption, color: colors.faintForeground },
  sampleText: { flex: 1, gap: 2 },
  sampleTitle: { ...type.bodySm, fontWeight: '700', color: colors.foreground },
  sampleHint: { ...type.caption, color: colors.mutedForeground },
  withdraw: {
    minHeight: 44,
    minWidth: 56,
    paddingHorizontal: space.sm,
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  withdrawText: { ...type.caption, fontWeight: '700', color: colors.destructive },
  pressed: { opacity: 0.6 },
  hint: { ...type.caption, color: colors.mutedForeground },
  notice: { ...type.bodySm, color: colors.accent },
  errorText: { ...type.bodySm, color: colors.destructive },
});
