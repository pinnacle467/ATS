import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Briefcase, CheckCircle2, MapPin } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useCareerSettings } from '@/pages/public/CareerPublicLayout';
import { api } from '@/lib/api';
import { careersPath, getTenantSlug } from '@/lib/tenant';

export default function CareerHomePage() {
  const settings = useCareerSettings();
  const [jobs, setJobs] = useState([]);
  const backendUrl = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    api.get('/career/public/jobs').then((r) => setJobs((r.data || []).slice(0, 6))).catch(() => {});
  }, []);

  const heroImageUrl = settings.hero_image_file_id
    ? `${backendUrl}/api/career/public/hero?tenant=${getTenantSlug() || ''}`
    : null;
  const heroStyle = heroImageUrl
    ? { backgroundImage: `linear-gradient(135deg, ${settings.primary_color}CC, ${(settings.secondary_color || settings.primary_color)}80), url(${heroImageUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }
    : { background: `linear-gradient(180deg, ${settings.primary_color}12, transparent)` };
  const heroTextClass = heroImageUrl ? 'text-white' : '';

  return (
    <div data-testid="career-home-page">
      {/* Hero */}
      <section className={`px-4 sm:px-6 py-20 sm:py-28 text-center ${heroTextClass}`} style={heroStyle} data-testid="career-hero-section">
        <div className="max-w-3xl mx-auto">
          <h1 className="font-display text-4xl sm:text-5xl font-semibold tracking-tight" data-testid="career-hero-headline">
            {settings.headline}
          </h1>
          <p className={`${heroImageUrl ? 'text-white/90' : 'text-muted-foreground'} text-lg mt-4`} data-testid="career-hero-subheadline">{settings.subheadline}</p>
          <div className="mt-8">
            <Link to={careersPath('/jobs')}>
              <Button size="lg" data-testid="career-hero-cta" style={{ background: settings.secondary_color || settings.primary_color, color: '#ffffff' }}>
                View Open Roles <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Featured jobs */}
      {jobs.length > 0 && (
        <section className="px-4 sm:px-6 py-16 max-w-6xl mx-auto">
          <h2 className="font-display text-2xl font-semibold mb-6">Featured Roles</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map((j) => (
              <Link
                key={j.id}
                to={careersPath(`/jobs/${j.slug}`)}
                className="border border-border rounded-xl p-5 hover:border-primary/50 hover:shadow-sm transition-all bg-card"
                data-testid={`career-featured-job-${j.id}`}
              >
                <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                  <Briefcase className="h-3.5 w-3.5" /> {j.department}
                </div>
                <h3 className="font-display font-semibold">{j.title}</h3>
                <div className="flex items-center gap-1 text-sm text-muted-foreground mt-2">
                  <MapPin className="h-3.5 w-3.5" /> {j.location || 'Remote'}
                </div>
                {j.employment_type && <Badge variant="outline" className="mt-3 text-xs">{j.employment_type}</Badge>}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Benefits */}
      {settings.benefits?.length > 0 && (
        <section className="px-4 sm:px-6 py-16 max-w-6xl mx-auto">
          <h2 className="font-display text-2xl font-semibold mb-6">Why join us</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {settings.benefits.map((b, i) => (
              <div key={i} className="flex items-center gap-3 p-4 rounded-xl bg-secondary/50" data-testid={`career-benefit-item-${i}`}>
                <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
                <span className="text-sm font-medium">{b}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* About */}
      {settings.about_text && (
        <section className="px-4 sm:px-6 py-16 max-w-3xl mx-auto text-center">
          <h2 className="font-display text-2xl font-semibold mb-4">About {settings.company_name}</h2>
          <p className="text-muted-foreground whitespace-pre-wrap">{settings.about_text}</p>
        </section>
      )}

      {/* CTA */}
      <section className="px-4 sm:px-6 py-16 text-center">
        <Link to={careersPath('/jobs')}>
          <Button size="lg" variant="outline" data-testid="career-bottom-cta">See All Open Roles</Button>
        </Link>
      </section>
    </div>
  );
}
