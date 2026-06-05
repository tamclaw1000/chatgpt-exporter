import cliProgress from 'cli-progress';
import chalk from 'chalk';

export function createProgressBar(total: number, label: string): cliProgress.SingleBar {
  const bar = new cliProgress.SingleBar({
    format: `${chalk.cyan(label)} |${chalk.cyan('{bar}')}| {percentage}% | {value}/{total} | ${chalk.dim('{topic}')}`,
    barCompleteChar: '\u2588',
    barIncompleteChar: '\u2591',
    hideCursor: true,
    gracefulExit: true,
  });
  bar.start(total, 0, { topic: '' });
  return bar;
}
