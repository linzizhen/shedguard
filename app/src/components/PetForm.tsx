/**
 * 宠物表单：新建/编辑两屏复用。
 * 校验规则与后端一致：name 必填非空 ≤64 字符；birth_date 可选 YYYY-MM-DD。
 */
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Card, Field, PrimaryButton, SecondaryButton, SectionTitle } from '@/components/ui';
import { colors } from '@/lib/theme';

/** 表单值：三个可选字段用空串表示「未填写」 */
export type PetFormValue = {
  name: string;
  species: string;
  morph: string;
  birth_date: string;
};

export const EMPTY_PET_FORM: PetFormValue = {
  name: '',
  species: '',
  morph: '',
  birth_date: '',
};

/** 校验：返回错误信息，null 表示通过 */
export function validatePetForm(value: PetFormValue): string | null {
  const name = value.name.trim();
  if (!name) return '名字不能为空';
  if (name.length > 64) return '名字最长 64 个字符';
  if (value.birth_date.trim()) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value.birth_date.trim())) {
      return '出生日期格式应为 YYYY-MM-DD';
    }
  }
  return null;
}

/** 把表单值转成提交体：空串转 undefined */
export function toPetInput(value: PetFormValue) {
  return {
    name: value.name.trim(),
    species: value.species.trim() || undefined,
    morph: value.morph.trim() || undefined,
    birth_date: value.birth_date.trim() || undefined,
  };
}

export function PetForm({
  initial,
  submitTitle,
  onSubmit,
  onCancel,
  submitting,
}: {
  initial?: PetFormValue;
  submitTitle: string;
  onSubmit: (value: PetFormValue) => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [value, setValue] = useState<PetFormValue>(initial ?? EMPTY_PET_FORM);
  const [error, setError] = useState<string | null>(null);

  function patch(key: keyof PetFormValue): (text: string) => void {
    return (text: string) => setValue((prev) => ({ ...prev, [key]: text }));
  }

  function handleSubmit(): void {
    const message = validatePetForm(value);
    if (message) {
      setError(message);
      return;
    }
    setError(null);
    onSubmit(value);
  }

  return (
    <Card style={styles.gapColumn}>
      <SectionTitle>基本信息</SectionTitle>
      <Field
        label="名字（必填）"
        value={value.name}
        onChangeText={patch('name')}
        placeholder="例：小橘"
        maxLength={64}
      />
      <Field
        label="物种（可选）"
        value={value.species}
        onChangeText={patch('species')}
        placeholder="例：豹纹守宫"
      />
      <Field
        label="基因/品系（可选）"
        value={value.morph}
        onChangeText={patch('morph')}
        placeholder="例：Normal"
      />
      <Field
        label="出生日期（可选，YYYY-MM-DD）"
        value={value.birth_date}
        onChangeText={patch('birth_date')}
        placeholder="例：2025-06-01"
        keyboardType="numbers-and-punctuation"
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.row}>
        <PrimaryButton title={submitTitle} onPress={handleSubmit} loading={submitting} />
      </View>
      <View style={styles.row}>
        <SecondaryButton title="取消" onPress={onCancel} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  gapColumn: {
    gap: 12,
  },
  row: {
    gap: 12,
  },
  error: {
    color: colors.destructive,
    fontSize: 13,
    fontWeight: '600',
  },
});
