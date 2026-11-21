import type { Metadata } from 'next';
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import { Workspace } from '@/components/workspace';
import './globals.css';

export const metadata: Metadata = {
  title: 'Spark Ready',
  description: 'Your workday, ready before you are.',
  icons: '/spark.svg',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Workspace>{children}</Workspace>
      </body>
    </html>
  );
}
