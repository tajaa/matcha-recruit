import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import type { BlogPost } from '../types';

interface BlogCarouselProps {
  posts: BlogPost[];
  limit?: number;
}

export function BlogCarousel({ posts, limit = 8 }: BlogCarouselProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    }).toUpperCase();
  };

  const checkScrollPosition = () => {
    if (!scrollContainerRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = scrollContainerRef.current;
    setCanScrollLeft(scrollLeft > 10);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
  };

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container) {
      container.addEventListener('scroll', checkScrollPosition);
      checkScrollPosition();
      return () => container.removeEventListener('scroll', checkScrollPosition);
    }
  }, [posts]);

  const scrollTo = (direction: 'left' | 'right') => {
    if (!scrollContainerRef.current) return;
    const cardWidth = scrollContainerRef.current.clientWidth * 0.35;
    scrollContainerRef.current.scrollBy({
      left: direction === 'left' ? -cardWidth : cardWidth,
      behavior: 'smooth'
    });
  };

  const displayPosts = posts.slice(0, limit);

  if (displayPosts.length === 0) {
    return (
      <div className="text-center py-16 border border-dashed border-zinc-300">
        <div className="w-12 h-12 mx-auto mb-4 border border-zinc-200 flex items-center justify-center">
          <span className="text-zinc-300 text-lg">∅</span>
        </div>
        <p className="text-zinc-400 text-[10px] tracking-[0.3em] uppercase">No Posts Available</p>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Left Arrow (desktop only) */}
      {canScrollLeft && (
        <button
          onClick={() => scrollTo('left')}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 hidden lg:flex w-10 h-10 items-center justify-center bg-white hover:bg-zinc-50 border border-zinc-200 shadow-sm transition-all"
          aria-label="Scroll left"
        >
          <ChevronLeft className="w-5 h-5 text-zinc-600" />
        </button>
      )}

      {/* Scroll Container */}
      <div
        ref={scrollContainerRef}
        className="flex gap-6 overflow-x-auto snap-x snap-mandatory scrollbar-hide pb-4 -mx-4 px-4 sm:mx-0 sm:px-0"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' } as React.CSSProperties}
      >
        {displayPosts.map((post) => (
          <Link
            key={post.id}
            to={`/blog/${post.slug}`}
            className="flex-none w-[280px] sm:w-[320px] snap-start group"
          >
            {/* Card Content */}
            <div className="bg-white transition-all duration-300 h-full flex flex-col">
              {/* Cover Image - Much larger, portrait-style */}
              <div className="aspect-[4/5] overflow-hidden bg-zinc-100 mb-4">
                {post.cover_image ? (
                  <img
                    src={post.cover_image}
                    alt={post.title}
                    loading="lazy"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-emerald-50 to-zinc-100 flex items-center justify-center">
                    <span className="text-6xl text-zinc-300">📝</span>
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex flex-col flex-1">
                {/* Date */}
                <div className="text-[9px] tracking-[0.2em] text-zinc-400 mb-3 font-medium">
                  {formatDate(post.published_at || post.created_at)}
                </div>

                {/* Title */}
                <h3 className="text-lg font-semibold text-zinc-900 mb-4 line-clamp-2 leading-tight">
                  {post.title}
                </h3>

                {/* Read Article Link */}
                <div className="mt-auto pt-4 border-t border-zinc-200 group-hover:border-emerald-500 transition-colors">
                  <span className="text-[10px] tracking-[0.2em] uppercase font-semibold text-zinc-900 group-hover:text-emerald-600 transition-colors flex items-center gap-2">
                    READ ARTICLE
                    <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Right Arrow (desktop only) */}
      {canScrollRight && (
        <button
          onClick={() => scrollTo('right')}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 hidden lg:flex w-10 h-10 items-center justify-center bg-white hover:bg-zinc-50 border border-zinc-200 shadow-sm transition-all"
          aria-label="Scroll right"
        >
          <ChevronRight className="w-5 h-5 text-zinc-600" />
        </button>
      )}

      <style>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-hide {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
}
