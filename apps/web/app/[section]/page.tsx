import { notFound } from 'next/navigation';
import { sections } from '@/lib/presentation';

export function generateStaticParams() {
  return sections
    .map(({ href }) => ({ section: href.slice(1) }))
    .filter(({ section }) => section);
}

export default async function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  if (!sections.some(({ href }) => href === `/${section}`)) notFound();
  return null;
}
