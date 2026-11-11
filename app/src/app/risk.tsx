/**
 * 卡皮风险评估（根级路由）：六道单选题 → POST /api/v1/risk-assessment → 结果。
 */
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, PageHeader, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import { useRiskAssessment } from '@/hooks/useRisk';
import { colors, radius } from '@/lib/theme';
import type { RiskAnswers, RiskAssessmentResult } from '@/lib/types';

type QuestionKey = keyof RiskAnswers;

interface Option {
  value: string;
  label: string;
}

interface Question {
  key: QuestionKey;
  title: string;
  options: Option[];
}

const QUESTIONS: Question[] = [
  {
    key: 'last_shed_complete',
    title: '上次蜕皮是否完整？',
    options: [
      { value: 'complete', label: '完整蜕下，无残留' },
      { value: 'partial_body', label: '身体有部分残留' },
      { value: 'large_retained', label: '大面积没蜕下来' },
    ],
  },
  {
    key: 'eye_condition',
    title: '眼睛周围有残留蜕皮吗？',
    options: [
      { value: 'clear', label: '干净，没有残留' },
      { value: 'retained_spectacle', label: '眼睛上有一层白膜/蜕皮' },
    ],
  },
  {
    key: 'toe_condition',
    title: '脚趾状况如何？',
    options: [
      { value: 'normal', label: '正常' },
      { value: 'swollen', label: '有脚趾肿大' },
      { value: 'discolored', label: '脚趾发黑/变色' },
    ],
  },
  {
    key: 'hydration',
    title: '平时补水频率？',
    options: [
      { value: 'daily', label: '几乎每天有饮水/喷雾' },
      { value: 'occasional', label: '偶尔' },
      { value: 'rarely_never', label: '很少或几乎没有' },
    ],
  },
  {
    key: 'humidity',
    title: '饲养箱湿度大概多少？',
    options: [
      { value: 'above_50', label: '50% 以上' },
      { value: '30_50', label: '30%–50%' },
      { value: 'below_30_unknown', label: '低于 30% 或不清楚' },
    ],
  },
  {
    key: 'water_bowl',
    title: '水盆情况？',
    options: [
      { value: 'fresh_daily', label: '每天换新鲜水' },
      { value: 'stale_or_absent', label: '不常换或没有水盆' },
    ],
  },
];

const LEVEL_META: Record<RiskAssessmentResult['level'], { label: string; color: string; bg: string }> = {
  low: { label: '风险较低', color: colors.success, bg: '#DCFCE7' },
  moderate: { label: '需要留意', color: colors.warning, bg: '#FEF3C7' },
  high: { label: '高风险', color: colors.destructive, bg: '#FEE2E2' },
};

export default function RiskScreen() {
  const [answers, setAnswers] = useState<Partial<Record<QuestionKey, string>>>({});
  const [result, setResult] = useState<RiskAssessmentResult | null>(null);
  const riskMutation = useRiskAssessment();

  const allAnswered = QUESTIONS.every((q) => answers[q.key] !== undefined);

  function handleSubmit() {
    if (!allAnswered) return;
    riskMutation.mutate(answers as RiskAnswers, {
      onSuccess: (data) => setResult(data),
      onError: () => setResult(null),
    });
  }

  function handleReset() {
    setAnswers({});
    setResult(null);
    riskMutation.reset();
  }

  if (result) {
    const meta = LEVEL_META[result.level];
    return (
      <Screen>
        <PageHeader title="评估结果" subtitle="根据你的回答给出的风险提示" />
        <Card style={[styles.resultCard, { borderColor: meta.color }]}>
          <View style={[styles.levelBadge, { backgroundColor: meta.bg }]}>
            <Text style={[styles.levelText, { color: meta.color }]}>{meta.label}</Text>
          </View>
          <Text style={styles.scoreText}>风险评分 {result.score}</Text>
          {result.factors.length > 0 ? (
            <View style={styles.factorList}>
              {result.factors.map((factor) => (
                <View key={factor.key} style={styles.factorRow}>
                  <Text style={styles.factorPoints}>+{factor.points}</Text>
                  <Text style={styles.factorDetail}>{factor.detail}</Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.factorEmpty}>没有发现明显的风险因素。</Text>
          )}
        </Card>
        {result.vet_warning ? (
          <Card style={styles.vetCard}>
            <Text style={styles.vetTitle}>需要就医</Text>
            <Text style={styles.vetText}>{result.vet_warning}</Text>
          </Card>
        ) : null}
        <SecondaryButton title="重新评估" onPress={handleReset} />
      </Screen>
    );
  }

  return (
    <Screen>
      <PageHeader title="卡皮风险评估" subtitle="回答六个问题，看看蜕皮不全的风险" />
      {QUESTIONS.map((question, qIndex) => (
        <Card key={question.key} style={styles.questionCard}>
          <Text style={styles.questionTitle}>
            {qIndex + 1}. {question.title}
          </Text>
          <View style={styles.optionList}>
            {question.options.map((option) => {
              const active = answers[question.key] === option.value;
              return (
                <Pressable
                  key={option.value}
                  onPress={() => setAnswers((prev) => ({ ...prev, [question.key]: option.value }))}
                  style={[styles.option, active && styles.optionActive]}
                >
                  <View style={[styles.radio, active && styles.radioActive]}>
                    {active ? <View style={styles.radioDot} /> : null}
                  </View>
                  <Text style={[styles.optionLabel, active && styles.optionLabelActive]}>{option.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </Card>
      ))}

      {riskMutation.isError ? (
        <Card>
          <EmptyState icon="alert-circle" title="提交失败" subtitle={riskMutation.error.message} />
        </Card>
      ) : null}

      <PrimaryButton
        title={!allAnswered ? '请回答全部问题' : riskMutation.isPending ? '评估中…' : '开始评估'}
        onPress={handleSubmit}
        loading={riskMutation.isPending}
        disabled={!allAnswered}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  questionCard: { gap: 12 },
  questionTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  optionList: { gap: 10 },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 3,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.card,
  },
  optionActive: { borderColor: colors.primary, backgroundColor: colors.background },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colors.mutedForeground,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioActive: { borderColor: colors.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary },
  optionLabel: { flex: 1, fontSize: 15, color: colors.foreground },
  optionLabelActive: { fontWeight: '700', color: colors.primaryDark },
  resultCard: { borderWidth: 3, gap: 12 },
  levelBadge: {
    alignSelf: 'flex-start',
    borderRadius: radius.md,
    paddingVertical: 6,
    paddingHorizontal: 16,
  },
  levelText: { fontSize: 18, fontWeight: '800' },
  scoreText: { fontSize: 15, fontWeight: '700', color: colors.foreground },
  factorList: { gap: 8 },
  factorRow: { flexDirection: 'row', gap: 10 },
  factorPoints: { fontSize: 14, fontWeight: '800', color: colors.destructive, width: 32 },
  factorDetail: { flex: 1, fontSize: 14, lineHeight: 20, color: colors.foreground },
  factorEmpty: { fontSize: 14, color: colors.mutedForeground },
  vetCard: { borderColor: colors.destructive, borderWidth: 3, gap: 6 },
  vetTitle: { fontSize: 15, fontWeight: '800', color: colors.destructive },
  vetText: { fontSize: 14, lineHeight: 21, color: colors.foreground },
});
