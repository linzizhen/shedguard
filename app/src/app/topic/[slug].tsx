/**
 * 知识详情页（根级路由，带 Stack 返回按钮）。
 * 后端：GET /api/v1/knowledge/topics/{slug}。
 */
import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, Screen } from '@/components/ui';
import { useKnowledgeTopic } from '@/hooks/useKnowledge';
import { colors, space, type } from '@/lib/theme';

export default function TopicDetailScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const topicQuery = useKnowledgeTopic(slug);

  if (topicQuery.isLoading) {
    return (
      <Screen>
        <Card>
          <EmptyState icon="hourglass-outline" title="加载中…" />
        </Card>
      </Screen>
    );
  }

  if (topicQuery.isError || !topicQuery.data) {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline-outline"
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
  title: {
    ...type.display,
    fontSize: 24,
    lineHeight: 32,
    color: colors.foreground,
  },
  summary: {
    ...type.body,
    color: colors.mutedForeground,
  },
  section: {
    gap: space.sm,
  },
  sectionHeading: {
    ...type.heading,
    color: colors.primaryDark,
  },
  bulletRow: {
    flexDirection: 'row',
    gap: space.sm,
    paddingRight: space.xs,
  },
  bulletDot: {
    ...type.body,
    fontWeight: '800',
    color: colors.primary,
  },
  bulletText: {
    flex: 1,
    ...type.body,
    color: colors.body,
  },
});