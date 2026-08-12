-- Seed data for BPMFlow AI procurement demonstration
-- Note: Run this after creating users in Supabase Auth

-- Sample resources (these don't depend on users)
INSERT INTO public.resources (name, type, capacity, availability_percentage, cost_per_hour, department, skills) VALUES
('Procurement Team', 'human', 5, 80, 50.00, 'Procurement', ARRAY['purchasing', 'negotiation', 'vendor_management']),
('Finance Team', 'human', 3, 60, 75.00, 'Finance', ARRAY['budget_approval', 'financial_analysis', 'compliance']),
('IT Equipment', 'equipment', 10, 100, 0.00, 'IT', ARRAY[]),
('Budget - Q1 2024', 'budget', 100000, 90, 0.00, 'Finance', ARRAY[]);

-- Note: Processes and tasks depend on users, so they should be created after user setup
-- You can create them through the application UI or uncomment and update with actual user IDs
