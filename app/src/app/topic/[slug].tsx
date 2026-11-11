/**
 * 知识详情页（根级路由，带 Stack 返回按钮）。
 * 后端：GET /api/v1/knowledge/topics/{slug}。
 */
import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, Screen } from '@/components/ui';
import { useKnowledgeTopic } from '@/hooks/useKnowledge';
import { colors } from '@/lib/theme';

export default function TopicDetailScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const topicQuery = useKnowledgeTopic(slug);

  if (topicQuery.isLoading) {
    return (
      <Screen>
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      </Screen>
    );
  }

  if (topicQuery.isError || !topicQuery.data) {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="无法加载这篇内容"
            subtitle={topicQuery.error?.message ?? '内容不存在'}
          />
        </Card>
      </Screen>
    );
  }

  const topic = topicQuery.data;

  return (
    <Screen>
      <Text style={styles.title}>{topic.title}</Text>
      <Text style={styles.summary}>{topic.summary}</Text>
      {topic.sections.map((section) => (
        <Card key={section.heading} style={styles.section}>
          <Text style={styles.sectionHeading}>{section.heading}</Text>
          {section.bullets.map((bullet, index) => (
            <View key={index} style={styles.bulletRow}>
              <Text style={styles.bulletDot}>•</Text>
              <Text style={styles.bulletText}>{bullet}</Text>
            </View>
          ))}
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 24, fontWeight: '800', color: colors.foreground },
  summary: { fontSize: 15, lineHeight: 22, color: colors.mutedForeground },
  section: { gap: 8 },
  sectionHeading: { fontSize: 17, fontWeight: '700', color: colors.primaryDark },
  bulletRow: { flexDirection: 'row', gap: 8, paddingRight: 4 },
  bulletDot: { fontSize: 15, color: colors.primary, fontWeight: '800', lineHeight: 22 },
  bulletText: { flex: 1, fontSize: 15, lineHeight: 22, color: colors.foreground },
});
