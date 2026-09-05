import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import PinnacleLogo from '@/components/PinnacleLogo';
import { api, errMsg } from '@/lib/api';

export default function WorkspacePickerPage() {
  const navigate = useNavigate();
  const [slug, setSlug] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const s = slug.trim().toLowerCase().replace(/[^a-z0-9-]/g, '');
    if (!s) {
      toast.error('Enter your workspace name');
      return;
    }
    setBusy(true);
    try {
      await api.get(`/tenants/by-slug/${s}`);
      navigate(`/${s}/login`);
    } catch (err) {
      toast.error(errMsg(err, 'Workspace not found'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6" data-testid="workspace-picker-page">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <PinnacleLogo size={40} />
          <div>
            <div className="font-display font-bold text-xl tracking-tight">HireFlow</div>
            <div className="text-xs text-muted-foreground">Multi-workspace applicant tracking</div>
          </div>
        </div>

        <h1 className="font-display text-2xl font-semibold tracking-tight mb-1">Find your workspace</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Every company has its own sign-in address, like <span className="font-mono text-foreground">/acme/login</span>.
        </p>

        <Card>
          <CardContent className="pt-6">
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="slug">Workspace</Label>
                <div className="flex items-center rounded-md border border-input bg-background focus-within:ring-2 focus-within:ring-ring">
                  <span className="pl-3 text-sm text-muted-foreground select-none">/</span>
                  <Input
                    id="slug"
                    data-testid="workspace-slug-input"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="acme"
                    className="border-0 focus-visible:ring-0 shadow-none px-1"
                  />
                  <span className="pr-3 text-sm text-muted-foreground select-none">/login</span>
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={busy} data-testid="workspace-continue-button">
                {busy ? 'Checking...' : 'Continue'} <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="mt-6 text-xs text-muted-foreground">
          Platform owner?{' '}
          <Link to="/platform/login" className="text-primary hover:underline font-medium" data-testid="platform-login-link">
            Sign in to the control panel
          </Link>
        </p>
      </div>
    </div>
  );
}
