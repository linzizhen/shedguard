/**
 * 蜕皮日志 Tab：宠物切换 + 下次蜕皮预测 + 蜕皮记录时间线 + 添加/完成/删除。
 * 后端：GET/POST /api/v1/pets/{id}/shed-records、GET /api/v1/pets/{id}/shed-prediction。
 */
import { Link } from 'expo-router';
import { useState, type ComponentProps } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { PetPicker } from '@/components/PetPicker';
import { Card, EmptyState, PageHeader, PrimaryButton, Screen, SectionTitle } from '@/components/ui';
import {
  useCreateShedRecord,
  useDeleteShedRecord,
  useShedPrediction,
  useShedRecords,
  useUpdateShedRecord,
} from '@/hooks/useShed';
import { usePets } from '@/hooks/usePets';
import { useServerUrl } from '@/lib/serverUrl';
import { todayIso, formatDateCn } from '@/lib/dates';
import { colors, radius } from '@/lib/theme';
import type { Pet, ShedPrediction, ShedRecord } from '@/lib/types';

function PredictionCard({ prediction }: { prediction: ShedPrediction }) {
  if (!prediction.predictable) {
    return (
      <Card style={[styles.predCard, { borderColor: colors.accent }]}>
        <Text style={styles.predTitle}>下次蜕皮预测</Text>
        <Text style={styles.predReason}>{prediction.reason}</Text>
      </Card>
    );
  }
  return (
    <Card style={[styles.predCard, { borderColor: colors.accent }]}>
      <Text style={styles.predTitle}>预计下次蜕皮窗口</Text>
      <Text style={styles.predWindow}>
        {prediction.next_window_start ? formatDateCn(prediction.next_window_start) : '—'} ~{' '}
        {prediction.next_window_end ? formatDateCn(prediction.next_window_end) : '—'}
      </Text>
      <Text style={styles.predMeta}>
        基于 {prediction.based_on_cycles} 个完整周期 · 中位间隔{' '}
        {prediction.median_interval_days ?? '—'} 天
      </Text>
    </Card>
  );
}

function RecordRow({
  record,
  onComplete,
  onDelete,
}: {
  record: ShedRecord;
  onComplete: () => void;
  onDelete: () => void;
}) {
  const ongoing = record.completed_on === null;
  return (
    <View style={styles.recordRow}>
      <View style={styles.recordDot} />
      <View style={styles.recordBody}>
        <View style={styles.recordHeader}>
          <Text style={styles.recordRange}>
            {formatDateCn(record.started_on)}
            {ongoing ? ' 开始' : ` ~ ${formatDateCn(record.completed_on as string)}`}
          </Text>
          {ongoing ? (
            <View style={styles.ongoingBadge}>
              <Text style={styles.ongoingText}>进行中</Text>
            </View>
          ) : null}
        </View>
        {record.notes ? <Text style={styles.recordNotes}>{record.notes}</Text> : null}
        <View style={styles.recordActions}>
          {ongoing ? (
            <Pressable onPress={onComplete} hitSlop={6}>
              <Text style={styles.actionComplete}>标记完成</Text>
            </Pressable>
          ) : null}
          <Pressable onPress={onDelete} hitSlop={6}>
            <Text style={styles.actionDelete}>删除</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

export default function LogScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const [selectedPetId, setSelectedPetId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [startedOn, setStartedOn] = useState(todayIso());
  const [completedOn, setCompletedOn] = useState('');
  const [notes, setNotes] = useState('');

  const pets: Pet[] = petsQuery.data?.items ?? [];
  const activePetId =
    selectedPetId && pets.some((p) => p.id === selectedPetId) ? selectedPetId : (pets[0]?.id ?? null);
  const activePet = pets.find((p) => p.id === activePetId) ?? null;

  const recordsQuery = useShedRecords(activePetId);
  const predictionQuery = useShedPrediction(activePetId);
  const createMutation = useCreateShedRecord(activePetId ?? '');
  const updateMutation = useUpdateShedRecord(activePetId ?? '');
  const deleteMutation = useDeleteShedRecord(activePetId ?? '');

  function resetForm() {
    setStartedOn(todayIso());
    setCompletedOn('');
    setNotes('');
    setShowForm(false);
  }

  function handleSubmit() {
    if (!activePetId) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(startedOn)) {
      Alert.alert('日期格式不对', '开始日期请用 YYYY-MM-DD，例如 2026-11-04');
      return;
    }
    if (completedOn && !/^\d{4}-\d{2}-\d{2}$/.test(completedOn)) {
      Alert.alert('日期格式不对', '结束日期请用 YYYY-MM-DD，或留空表示仍在蜕皮中');
      return;
    }
    createMutation.mutate(
      {
        started_on: startedOn,
        completed_on: completedOn || undefined,
        notes: notes.trim() || undefined,
      },
      {
        onSuccess: resetForm,
        onError: (error: Error) => Alert.alert('保存失败', error.message),
      },
    );
  }

  function handleComplete(record: ShedRecord) {
    updateMutation.mutate(
      { recordId: record.id, input: { started_on: record.started_on, completed_on: todayIso() } },
      { onError: (error: Error) => Alert.alert('更新失败', error.message) },
    );
  }

  function handleDelete(record: ShedRecord) {
    Alert.alert('删除这条记录？', `${formatDateCn(record.started_on)} 的蜕皮记录将被删除，不可恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () =>
          deleteMutation.mutate(record.id, {
            onError: (error: Error) => Alert.alert('删除失败', error.message),
          }),
      },
    ]);
  }

  if (serverUrl === '') {
    return (
      <Screen>
        <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="先配置服务器"
            subtitle="到「设置」页填写服务器地址，才能记录与查看蜕皮日志"
          />
        </Card>
      </Screen>
    );
  }

  if (petsQuery.isLoading) {
    return (
      <Screen>
        <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      </Screen>
    );
  }

  if (petsQuery.isError) {
    return (
      <Screen>
        <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />
        <Card>
          <EmptyState icon="cloud-offline" title="无法加载宠物列表" subtitle={petsQuery.error.message} />
        </Card>
      </Screen>
    );
  }

  if (pets.length === 0) {
    return (
      <Screen>
        <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />
        <Card>
          <EmptyState icon="paw" title="还没有添加宠物" subtitle="先到「设置」页添加一只宠物" />
        </Card>
      </Screen>
    );
  }

  const records: ShedRecord[] = recordsQuery.data?.items ?? [];

  return (
    <Screen>
      <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />

      {pets.length > 0 ? (
        <>
          <PetPicker pets={pets} selectedId={activePetId} onSelect={setSelectedPetId} />

          {predictionQuery.data ? <PredictionCard prediction={predictionQuery.data} /> : null}

          <View style={styles.sectionHeader}>
            <SectionTitle>蜕皮记录{activePet ? ` · ${activePet.name}` : ''}</SectionTitle>
            <Pressable onPress={() => (showForm ? resetForm() : setShowForm(true))} hitSlop={6}>
              <Text style={styles.addLink}>{showForm ? '取消' : '+ 添加'}</Text>
            </Pressable>
          </View>

          {showForm ? (
            <Card style={styles.formCard}>
              <Field label="开始日期 *" value={startedOn} onChangeText={setStartedOn} placeholder="YYYY-MM-DD" />
              <Field
                label="结束日期（留空 = 进行中）"
                value={completedOn}
                onChangeText={setCompletedOn}
                placeholder="YYYY-MM-DD"
              />
              <Field label="备注" value={notes} onChangeText={setNotes} placeholder="可选，例如：尾部残留" />
              <PrimaryButton
                title={createMutation.isPending ? '保存中…' : '保存记录'}
                onPress={handleSubmit}
                loading={createMutation.isPending}
              />
            </Card>
          ) : null}

          {recordsQuery.isLoading ? (
            <Card>
              <EmptyState icon="hourglass" title="加载中…" />
            </Card>
          ) : recordsQuery.isError ? (
            <Card>
              <EmptyState icon="cloud-offline" title="无法加载记录" subtitle={recordsQuery.error.message} />
            </Card>
          ) : records.length === 0 ? (
            <Card>
              <EmptyState icon="calendar" title="还没有蜕皮记录" subtitle="每次蜕皮后记一条，累积几次就能预测下次" />
            </Card>
          ) : (
            <Card style={styles.timelineCard}>
              {records.map((record, index) => (
                <View key={record.id} style={index < records.length - 1 ? styles.recordWrapper : undefined}>
                  <RecordRow
                    record={record}
                    onComplete={() => handleComplete(record)}
                    onDelete={() => handleDelete(record)}
                  />
                </View>
              ))}
            </Card>
          )}

          <Link href="/risk" asChild>
            <Pressable style={({ pressed }) => [styles.riskEntry, pressed && styles.riskPressed]}>
              <View style={styles.riskEntryBody}>
                <Text style={styles.riskEntryTitle}>卡皮风险评估</Text>
                <Text style={styles.riskEntrySubtitle}>回答六个问题，看看有没有蜕皮不全的风险</Text>
              </View>
              <Text style={styles.riskEntryChevron}>›</Text>
            </Pressable>
          </Link>
        </>
      ) : (
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      )}
    </Screen>
  );
}

/** 表单输入框（避免与 ui.tsx 的 Field 重复 import 冲突，这里简单内联） */
function Field({
  label,
  ...props
}: { label: string } & ComponentProps<typeof TextInput>) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        placeholderTextColor={colors.mutedForeground}
        {...props}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  predCard: { borderWidth: 3, gap: 6 },
  predTitle: { fontSize: 14, fontWeight: '700', color: colors.accent },
  predWindow: { fontSize: 22, fontWeight: '800', color: colors.foreground },
  predMeta: { fontSize: 13, color: colors.mutedForeground },
  predReason: { fontSize: 14, lineHeight: 21, color: colors.foreground },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  addLink: { fontSize: 15, fontWeight: '700', color: colors.primary },
  formCard: { gap: 12 },
  fieldWrap: { gap: 6 },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: colors.foreground },
  fieldInput: {
    borderWidth: 3,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: 10,
    paddingHorizontal: 12,
    fontSize: 15,
    color: colors.foreground,
    backgroundColor: colors.card,
  },
  timelineCard: { gap: 0 },
  recordWrapper: {
    borderBottomWidth: 2,
    borderBottomColor: colors.muted,
  },
  recordRow: { flexDirection: 'row', gap: 12, paddingVertical: 12 },
  recordDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.primary,
    marginTop: 5,
  },
  recordBody: { flex: 1, gap: 4 },
  recordHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  recordRange: { fontSize: 15, fontWeight: '700', color: colors.foreground },
  ongoingBadge: {
    backgroundColor: '#DBEAFE',
    borderRadius: 8,
    paddingVertical: 2,
    paddingHorizontal: 8,
  },
  ongoingText: { fontSize: 11, fontWeight: '700', color: colors.accent },
  recordNotes: { fontSize: 13, color: colors.mutedForeground },
  recordActions: { flexDirection: 'row', gap: 16, marginTop: 2 },
  actionComplete: { fontSize: 13, fontWeight: '700', color: colors.success },
  actionDelete: { fontSize: 13, fontWeight: '700', color: colors.destructive },
  riskEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 3,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: 16,
    gap: 12,
  },
  riskPressed: { opacity: 0.85 },
  riskEntryBody: { flex: 1, gap: 3 },
  riskEntryTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  riskEntrySubtitle: { fontSize: 13, color: colors.mutedForeground },
  riskEntryChevron: { fontSize: 26, color: colors.primary, fontWeight: '300' },
});
