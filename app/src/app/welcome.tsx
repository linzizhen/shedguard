/**
 * 首次使用向导：欢迎 → 给守宫起名字 → 准备拍照。
 * 目标：不懂技术的人也能走完，全程不出现「服务器」「置信度」这类词。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, Field, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import { useCreatePet } from '@/hooks/usePets';
import { markOnboarded } from '@/lib/onboarding';
import { saveServerUrl, useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';

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
        <View style={styles.hero}>
          <View style={styles.badge}>
            <Ionicons name="link-outline" size={30} color={colors.primary} />
          </View>
          <Text style={styles.title}>先连上电脑</Text>
          <Text style={styles.subtitle}>
            这个 App 需要和电脑上的一个小程序配合。把那个程序的地址填在下面（不知道就问帮你安装的人）。
          </Text>
        </View>

        <Card style={{ gap: 14 }}>
          <Field
            label="电脑上那个程序的地址"
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
        </Card>

        <SecondaryButton title="先随便看看" onPress={() => void finish()} />
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={styles.progress}>
        {STEPS.map((label, index) => (
          <View key={label} style={styles.progressItem}>
            <View style={[styles.dot, index <= step && styles.dotActive]} />
            <Text style={[styles.dotLabel, index === step && styles.dotLabelActive]}>{label}</Text>
          </View>
        ))}
      </View>

      {step === 0 ? (
        <>
          <View style={styles.hero}>
            <View style={styles.badge}>
              <Ionicons name="paw" size={34} color={colors.primary} />
            </View>
            <Text style={styles.title}>让小守宫的蜕皮不再错过</Text>
            <Text style={styles.subtitle}>
              拍一张照片，它就会告诉你守宫是不是要蜕皮了。整个过程只要几秒。
            </Text>
          </View>

          <Card style={{ gap: 12 }}>
            <Text style={styles.cardTitle}>怎么用</Text>
            <Step text="把手机对准守宫身上发白的地方" index={1} />
            <Step text="点一下拍照，等几秒" index={2} />
            <Step text="看结果：正在蜕皮 / 还没到" index={3} />
          </Card>

          <PrimaryButton title="开始" onPress={() => setStep(1)} />
          <TextButton title="跳过" onPress={() => void finish()} />
        </>
      ) : null}

      {step === 1 ? (
        <>
          <View style={styles.hero}>
            <View style={styles.badge}>
              <Ionicons name="create-outline" size={30} color={colors.primary} />
            </View>
            <Text style={styles.title}>给它起个名字</Text>
            <Text style={styles.subtitle}>以后记录和提醒里都会用这个名字，随便起。</Text>
          </View>

          <Card style={{ gap: 14 }}>
            <Field
              label="名字"
              placeholder="比如：小橘子"
              value={name}
              maxLength={20}
              onChangeText={setName}
            />

            <View style={{ gap: 8 }}>
              <Text style={styles.fieldLabel}>是哪一种（不确定就保持第一个）</Text>
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
          </Card>
        </>
      ) : null}

      {step === 2 ? (
        <>
          <View style={styles.hero}>
            <View style={styles.badge}>
              <Ionicons name="checkmark" size={34} color={colors.primary} />
            </View>
            <Text style={styles.title}>准备好了</Text>
            <Text style={styles.subtitle}>
              {trimmedName.length > 0 ? `${trimmedName}的档案已经建好。` : '档案已经建好。'}
              现在拍第一张照片试试吧。
            </Text>
          </View>

          <Card style={{ gap: 10 }}>
            <Text style={styles.cardTitle}>拍照小提示</Text>
            <Text style={styles.bullet}>· 光线要亮，别开闪光灯</Text>
            <Text style={styles.bullet}>· 让守宫占满画面中间</Text>
            <Text style={styles.bullet}>· 重点拍身上发白的地方</Text>
          </Card>

          <PrimaryButton title="去拍第一张" onPress={() => void finish()} />
          <TextButton title="稍后再说" onPress={() => void finish()} />
        </>
      ) : null}
    </Screen>
  );
}

/** 文字按钮：只做次要动作，不抢主按钮的注意力 */
function TextButton({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={styles.textButton}>
      <Text style={styles.textButtonLabel}>{title}</Text>
    </Pressable>
  );
}

function Step({ text, index }: { text: string; index: number }) {
  return (
    <View style={styles.stepRow}>
      <View style={styles.stepIndex}>
        <Text style={styles.stepIndexText}>{index}</Text>
      </View>
      <Text style={styles.stepText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    marginTop: 16,
    alignItems: 'center',
    gap: 12,
  },
  badge: {
    width: 84,
    height: 84,
    borderRadius: radius.xl,
    backgroundColor: colors.card,
    borderWidth: 3,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.foreground,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 15,
    lineHeight: 23,
    color: colors.mutedForeground,
    textAlign: 'center',
    paddingHorizontal: 8,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.foreground,
  },
  bullet: {
    fontSize: 15,
    lineHeight: 22,
    color: colors.foreground,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepIndex: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepIndexText: {
    fontSize: 13,
    fontWeight: '800',
    color: colors.primaryDark,
  },
  stepText: {
    flex: 1,
    fontSize: 15,
    color: colors.foreground,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.foreground,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.muted,
    minHeight: 44,
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryDark,
  },
  chipText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.mutedForeground,
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  hint: {
    fontSize: 13,
    color: colors.mutedForeground,
    textAlign: 'center',
  },
  error: {
    fontSize: 14,
    color: colors.destructive,
    textAlign: 'center',
  },
  progress: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 18,
    marginBottom: 4,
  },
  progressItem: {
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
  },
  dotActive: {
    backgroundColor: colors.primary,
  },
  dotLabel: {
    fontSize: 11,
    color: colors.mutedForeground,
  },
  dotLabelActive: {
    color: colors.primaryDark,
    fontWeight: '700',
  },
  textButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textButtonLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
});
