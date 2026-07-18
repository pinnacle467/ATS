import { useEffect, useState } from 'react';
import { useParams, Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '@/lib/api';
import { useCareerSettings } from './CareerPublicLayout';

// Renders one of the 4 published static pages (About, Benefits, Life, Testimonials).
// Route params drive the `key`. Uses the shared CareerPublicLayout for header/footer.
export default function CareerStaticPage() {
  const { key } = useParams();
  const settings = useCareerSettings();
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    setPage(null);
    api
      .get(`/career/public/pages/${key}`)
      .then((r) => setPage(r.data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [key]);

  // Update document title + meta description per page for SEO
  useEffect(() => {
    if (!page || !settings) return;
    const title = `${page.title} — ${settings.company_name || 'Careers'}`;
    document.title = title;
    const desc = page.meta_description || settings.meta_description || settings.subheadline || '';
    setMeta('description', desc);
    setMeta('og:title', title, true);
    setMeta('og:description', desc, true);
    setMeta('og:type', 'website', true);
    setMeta('og:url', window.location.href, true);
    setMeta('og:image', `${backendUrl}/api/career/public/og-image`, true);
  }, [page, settings, backendUrl]);

  if (loading) {
    return <div className="min-h-[50vh] flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }
  if (notFound || !page) {
    return <Navigate to="/careers" replace />;
  }

  const brandGradient = `linear-gradient(135deg, ${settings.primary_color}CC, ${settings.secondary_color || settings.primary_color}CC)`;

  return (
    <div data-testid={`career-static-page-${key}`}>
      <section className="relative overflow-hidden" style={{ background: brandGradient }}>
        {page.hero_image_file_id && (
          <img
            src={`${backendUrl}/api/career/public/pages/${key}/hero`}
            alt=""
            className="absolute inset-0 h-full w-full object-cover opacity-40"
          />
        )}
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 py-16 md:py-24 text-white">
          <h1 className="font-display text-3xl md:text-5xl font-semibold tracking-tight">{page.hero_heading || page.title}</h1>
          {page.hero_subheading && (
            <p className="mt-3 text-white/90 text-base md:text-lg max-w-2xl">{page.hero_subheading}</p>
          )}
        </div>
      </section>

      <article className="max-w-3xl mx-auto px-4 sm:px-6 py-12 prose prose-neutral prose-lg max-w-none">
        {page.body_markdown ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{page.body_markdown}</ReactMarkdown>
        ) : (
          <p className="text-muted-foreground italic">Content coming soon.</p>
        )}
      </article>
    </div>
  );
}

// Small helper to set/create a <meta> tag by name (or property for OG tags)
function setMeta(name, content, isProperty = false) {
  if (!content) return;
  const attr = isProperty ? 'property' : 'name';
  let tag = document.head.querySelector(`meta[${attr}="${name}"]`);
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attr, name);
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', content);
}

export { setMeta };
