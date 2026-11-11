/**
 * 卡皮风险评估（一次性提交，用 mutation）。
 */
import { useMutation } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import type { RiskAnswers, RiskAssessmentResult } from '@/lib/types';

export function useRiskAssessment() {
  return useMutation({
    mutationFn: (answers: RiskAnswers) =>
      apiFetch<RiskAssessmentResult>('/api/v1/risk-assessment', {
        method: 'POST',
        body: JSON.stringify(answers),
      }),
  });
}
