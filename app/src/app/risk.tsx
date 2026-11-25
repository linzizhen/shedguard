/**
 * 卡皮风险评估（根级路由）：六道单选题 → POST /api/v1/risk-assessment → 结果。
 * 纸感极简（P34）：题目用编号 + 1px 纸线分段，选项用方形标记而不是卡片框。
 */
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Divider,
  Eyebrow,
  Marker,
  PrimaryButton,
  Screen,
  SecondaryButton,
} from '@/components/ui';
import { useRiskAssessment } from '@/hooks/useRisk';
import { colors, hairline, radius, space, type } from '@/lib/theme';
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

const LEVEL_META: Record<
  RiskAssessmentResult['level'],
  { label: string; tone: 'success' | 'warning' | 'danger' }
> = {
  low: { label: '风险较低', tone: 'success' },
  moderate: { label: '需要留意', tone: 'warning' },
  high: { label: '高风险', tone: 'danger' },
};

const TONE_COLOR: Record<'success' | 'warning' | 'danger', string> = {
  success: colors.success,
  warning: colors.warning,
  danger: colors.destructive,
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
    const color = TONE_COLOR[meta.tone];
    return (
      <Screen>
        <Text style={styles.intro}>根据你的回答给出的风险提示，仅供参考，不替代看诊。</Text>

        <Divider />

        <View style={styles.levelRow}>
          <Marker tone={meta.tone} />
          <Text style={[styles.levelText, { color }]}>{meta.label}</Text>
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

        {result.vet_warning ? (
          <View style={styles.vetBlock}>
            <Eyebrow>需要就医</Eyebrow>
            <Text style={styles.vetText}>{result.vet_warning}</Text>
          </View>
        ) : null}

        <Divider />
        <SecondaryButton title="重新评估" onPress={handleReset} />
      </Screen>
    );
  }

  return (
    <Screen>
      <Text style={styles.intro}>回答六个问题，看看蜕皮不全的风险。</Text>

      <Divider />

      {QUESTIONS.map((question, qIndex) => (
        <View key={question.key} style={styles.questionBlock}>
          <View style={styles.questionHead}>
            <Text style={styles.questionIndex}>{`0${qIndex + 1}`}</Text>
            <Text style={styles.questionTitle}>{question.title}</Text>
          </View>
          <View style={styles.optionList}>
            {question.options.map((option) => {
              const active = answers[question.key] === option.value;
              return (
                <Pressable
                  key={option.value}
                  onPress={() => setAnswers((prev) => ({ ...prev, [question.key]: option.value }))}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: active }}
                  style={({ pressed }) => [styles.option, pressed && styles.optionPressed]}
                >
                  <View style={[styles.box, active && styles.boxActive]} />
                  <Text style={[styles.optionLabel, active && styles.optionLabelActive]}>
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}

      {riskMutation.isError ? (
        <Text style={styles.errorText}>提交失败：{riskMutation.error.message}</Text>
      ) : null}

      <Divider />

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
  intro: { ...type.bodySm, color: colors.mutedForeground },
  questionBlock: { gap: space.sm },
  questionHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.md,
  },
  questionIndex: {
    ...type.caption,
    fontWeight: '700',
    color: colors.accent,
    letterSpacing: 1,
    width: 24,
  },
  questionTitle: { ...type.heading, flex: 1, color: colors.foreground },
  optionList: { gap: 0, paddingLeft: 24 },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    minHeight: 44,
  },
  optionPressed: { opacity: 0.62 },
  box: {
    width: 12,
    height: 12,
    borderRadius: radius.xs,
    borderWidth: hairline,
    borderColor: colors.ghostForeground,
  },
  boxActive: {
    backgroundColor: colors.foreground,
    borderColor: colors.foreground,
  },
  optionLabel: { ...type.body, flex: 1, color: colors.mutedForeground },
  optionLabelActive: { fontWeight: '600', color: colors.foreground },
  levelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  levelText: { ...type.title },
  scoreText: { ...type.bodySm, color: colors.mutedForeground },
  factorList: { gap: space.sm },
  factorRow: { flexDirection: 'row', gap: space.sm },
  factorPoints: { ...type.bodySm, fontWeight: '700', color: colors.accent, width: 32 },
  factorDetail: { ...type.bodySm, flex: 1, color: colors.body },
  factorEmpty: { ...type.bodySm, color: colors.mutedForeground },
  vetBlock: { gap: space.xs },
  vetText: { ...type.bodySm, color: colors.body },
  errorText: { ...type.bodySm, color: colors.destructive },
});
