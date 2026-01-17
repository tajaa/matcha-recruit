import {
  Hash,
  MessageCircle,
  Megaphone,
  HelpCircle,
  Code,
  Coffee,
  Users,
  Sparkles,
  Briefcase,
  BookOpen,
  Lightbulb,
  Rocket,
  Bug,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

// Map room slugs/names to Lucide icons
const iconMap: Record<string, LucideIcon> = {
  // By slug
  general: MessageCircle,
  announcements: Megaphone,
  help: HelpCircle,
  support: HelpCircle,
  dev: Code,
  development: Code,
  engineering: Code,
  tech: Code,
  lounge: Coffee,
  random: Coffee,
  offtopic: Coffee,
  'off-topic': Coffee,
  community: Users,
  introductions: Users,
  ideas: Lightbulb,
  suggestions: Lightbulb,
  feedback: Lightbulb,
  jobs: Briefcase,
  careers: Briefcase,
  hiring: Briefcase,
  resources: BookOpen,
  learning: BookOpen,
  tutorials: BookOpen,
  showcase: Sparkles,
  projects: Rocket,
  launches: Rocket,
  bugs: Bug,
  issues: Bug,
  tools: Wrench,
};

interface RoomIconProps {
  slug?: string;
  name?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const sizeClasses = {
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
  xl: 'w-8 h-8',
};

export function RoomIcon({ slug, name, className = '', size = 'md' }: RoomIconProps) {
  // Try to find icon by slug first, then by name words
  let Icon: LucideIcon = Hash;

  if (slug && iconMap[slug.toLowerCase()]) {
    Icon = iconMap[slug.toLowerCase()];
  } else if (name) {
    // Try matching by words in the name
    const words = name.toLowerCase().split(/\s+/);
    for (const word of words) {
      if (iconMap[word]) {
        Icon = iconMap[word];
        break;
      }
    }
  }

  return <Icon className={`${sizeClasses[size]} ${className}`} />;
}
