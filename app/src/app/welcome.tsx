/**
 * 首次使用向导：欢迎 → 给守宫起名字 → 准备拍照。
 * 目标：不懂技术的人也能走完，全程不出现「服务器」「置信度」这类词。
 * 纸感极简（P34）：不用图标底座，靠大字标题、编号步骤与 1px 纸线分层。
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  BrandBar,
  Divider,
  Field,
  PrimaryButton,
  Screen,
  TextLink,
} from '@/components/ui';
import { useCreatePet } from '@/hooks/usePets';
import { markOnboarded } from '@/lib/onboarding';
import { saveServerUrl, useServerUrl } from '@/lib/serverUrl';
import { colors, hairline, radius, space, type } from '@/lib/theme';

const STEPS = ['欢迎', '起名字', '开始'];
const SPECIES = ['豹纹守宫', '肥尾守宫', '其他'];

export default function WelcomeScreen() {
  const serverUrl = useServerUrl();
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [species, setSpecies] = useState<string>(SPECIES[0]);
  const [addressDraft, setAddressDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const createPet = useCreatePet();

  const trimmedName = name.trim();
  const needsAddress = serverUrl === '';

  async function finish() {
    await markOnboarded();
    router.replace('/(tabs)');
  }

  async function handleSaveName() {
    if (trimmedName.length === 0) return;
    setError(null);
    try {
      await createPet.mutateAsync({ name: trimmedName, species });
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败，请再试一次');
    }
  }

  async function handleSaveAddress() {
    const value = addressDraft.trim();
    if (value.length === 0) return;
    await saveServerUrl(value);
    setError(null);
  }

  // 没有地址时先解决「连不上」这一件事，否则建宠物一定失败
  if (needsAddress) {
    return (
      <Screen>
        <BrandBar />
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>第一次使用</Text>
          <Text style={styles.title}>先连上服务端</Text>
          <Text style={styles.subtitle}>
            这个 App 需要和电脑上的一个小程序配合。把那个程序的地址填在下面（不知道就问帮你安装的人）。
          </Text>
        </View>

        <Field
          label="服务端地址"
          placeholder="例如 http://192.168.1.10:8000"
          autoCapitalize="none"
          autoCorrect={false}
          value={addressDraft}
          onChangeText={setAddressDraft}
        />
        <PrimaryButton
          title="连一下"
          onPress={() => void handleSaveAddress()}
          disabled={addressDraft.trim().length === 0}
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Divider />
        <TextLink title="先随便看看" onPress={() => void finish()} />
      </Screen>
    );
  }

  return (
    <Screen>
      <BrandBar />

      <View style={styles.progress}>
        {STEPS.map((label, index) => (
          <View key={label} style={styles.progressItem}>
            <View style={[styles.tick, index <= step && styles.tickActive]} />
            <Text style={[styles.tickLabel, index === step && styles.tickLabelActive]}>{label}</Text>
          </View>
        ))}
      </View>

      {step === 0 ? (
        <>
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>守宫蜕皮小助手</Text>
            <Text style={styles.title}>别错过它蜕皮的那几天</Text>
            <Text style={styles.subtitle}>
              拍一张照片，它就会告诉你守宫是不是要蜕皮了。整个过程只要几秒。
            </Text>
          </View>

          <Divider />

          <View style={styles.stepsBlock}>
            <Step text="把手机对准守宫身上发白的地方" index={1} />
            <Step text="点一下拍照，等几秒" index={2} />
            <Step text="看结果：正在蜕皮 / 还没到" index={3} />
          </View>

          <PrimaryButton title="开始" onPress={() => setStep(1)} />
          <TextLink title="跳过" onPress={() => void finish()} />
        </>
      ) : null}

      {step === 1 ? (
        <>
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>第 2 步</Text>
            <Text style={styles.title}>给它起个名字</Text>
            <Text style={styles.subtitle}>以后记录和提醒里都会用这个名字，随便起。</Text>
          </View>

          <Field
            label="名字"
            placeholder="比如：小橘子"
            value={name}
            maxLength={20}
            onChangeText={setName}
          />

          <View style={styles.speciesBlock}>
            <Text style={styles.eyebrow}>是哪一种（不确定就保持第一个）</Text>
            <View style={styles.chips}>
              {SPECIES.map((item) => {
                const active = item === species;
                return (
                  <Pressable
                    key={item}
                    onPress={() => setSpecies(item)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    style={[styles.chip, active && styles.chipActive]}
                  >
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{item}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          <PrimaryButton
            title="保存，下一步"
            onPress={() => void handleSaveName()}
            loading={createPet.isPending}
            disabled={trimmedName.length === 0}
          />
          {trimmedName.length === 0 ? (
            <Text style={styles.hint}>给它起个名字吧</Text>
          ) : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}
        </>
      ) : null}

      {step === 2 ? (
        <>
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>第 3 步</Text>
            <Text style={styles.title}>准备好了</Text>
            <Text style={styles.subtitle}>
              {trimmedName.length > 0 ? `${trimmedName}的档案已经建好。` : '档案已经建好。'}
              现在拍第一张照片试试吧。
            </Text>
          </View>

          <Divider />

          <View style={styles.stepsBlock}>
            <Text style={styles.bullet}>光线要亮，别开闪光灯</Text>
            <Text style={styles.bullet}>让守宫占满画面中间</Text>
            <Text style={styles.bullet}>重点拍身上发白的地方</Text>
          </View>

          <PrimaryButton title="去拍第一张" onPress={() => void finish()} />
          <TextLink title="稍后再说" onPress={() => void finish()} />
        </>
      ) : null}
    </Screen>
  );
}

function Step({ text, index }: { text: string; index: number }) {
  return (
    <View style={styles.stepRow}>
      <Text style={styles.stepIndex}>{`0${index}`}</Text>
      <Text style={styles.stepText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    marginTop: space.xl,
    gap: space.md,
  },
  eyebrow: {
    ...type.label,
    color: colors.faintForeground,
  },
  title: {
    ...type.display,
    color: colors.foreground,
  },
  subtitle: {
    ...type.body,
    color: colors.mutedForeground,
    maxWidth: 320,
  },
  bullet: {
    ...type.bodySm,
    color: colors.body,
  },
  stepsBlock: {
    gap: space.lg,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.md,
  },
  stepIndex: {
    ...type.caption,
    fontWeight: '700',
    color: colors.accent,
    letterSpacing: 1,
    width: 24,
  },
  stepText: {
    flex: 1,
    ...type.body,
    color: colors.body,
  },
  speciesBlock: {
    gap: space.sm,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    paddingHorizontal: space.lg,
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
    minHeight: 42,
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: colors.foreground,
    borderColor: colors.foreground,
  },
  chipText: {
    ...type.bodySm,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
  chipTextActive: {
    color: colors.onPrimary,
  },
  hint: {
    ...type.caption,
    color: colors.mutedForeground,
  },
  error: {
    ...type.bodySm,
    color: colors.destructive,
  },
  progress: {
    flexDirection: 'row',
    gap: space.lg,
    marginTop: space.lg,
  },
  progressItem: {
    alignItems: 'flex-start',
    gap: 6,
    flex: 1,
  },
  tick: {
    height: 2,
    width: '100%',
    backgroundColor: colors.border,
  },
  tickActive: {
    backgroundColor: colors.foreground,
  },
  tickLabel: {
    ...type.caption,
    fontSize: 11,
    color: colors.ghostForeground,
  },
  tickLabelActive: {
    color: colors.foreground,
    fontWeight: '700',
  },
});
