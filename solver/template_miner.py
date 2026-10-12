from solver.options import SynthesisOptions
from z3 import *
from examples.game import *
from common.util import *
from solver.beliefs import *
from solver.observations import *

class TemplateMiner:
    def __init__(self, game, isReal=True, generalization_threshold=5, min_bad_templates=1, aggressive_point_memory=False, options=None):
        """
        Initialize the TemplateMiner.
        
        Args:
            game: The game object
            isReal: Retained for API compatibility; numeric holes keep the replaced numeral's sort
            generalization_threshold: Number of level 0 templates required before attempting generalization
            min_bad_templates: Maximum number of remaining concrete templates for retrying the same generalization level
            aggressive_point_memory: Lift every coordinate of exact point templates to memory
        """
        self.options = options if options is not None else SynthesisOptions()
        self.aggressive_point_memory = aggressive_point_memory
        self.game = game
        self.isReal = isReal
        self.generalization_threshold = generalization_threshold
        self.min_bad_templates = min_bad_templates
        self._finite_domains = None
        self._fixed_domain_cache = {}

    def check_template_ubiquitousness(self, belief_formula, valid_h, template, memory_vars, latent_vars):

        s = Solver()
        equivalence = ForAll(latent_vars, And(Implies(belief_formula, template), Implies(template, belief_formula)))
        formula = ForAll(memory_vars, And(valid_h, Not(equivalence)))
        s.add(formula)
        res = s.check() 
        if res == sat:
            #print(s.model())
            return (False, s.model())
        elif res == unsat:
            return (True, None)
        if self.options.strict_template_checks:
            raise RuntimeError('Template ubiquitousness check unknown: ' + s.reason_unknown())
        return (True, None)  # Non-strict mode accepts an unknown result.
        
    def mine_template(self, model, h_vars, belief_formula):
        """
        Mine a template by substituting history variables with their concrete values from the model.
        
        Args:
            model: Z3 model containing valuations for history variables
            h_vars: List of history variables to substitute
            belief_formula: The belief formula containing history variables
            
        Returns:
            Template formula with history variables replaced by concrete values
        """
        # Build substitution list: (h_var, concrete_value) pairs
        substitutions = []
        for h_var in h_vars:
            # Get the concrete value from the model
            concrete_value = model.eval(h_var, model_completion=True)
            substitutions.append((h_var, concrete_value))
        
        # Substitute all history variables with their concrete values
        template = substitute(belief_formula, substitutions)
        #print(template)
        # Simplify the resulting template
        template = recur_simplify(template, Bool(True))
        
        return template

    def mine_templates(self, old_templates, belief_formula, valid_h, h_vars, memory_vars, latent_vars, max_iterations=100):
        """
        Mine templates iteratively until ubiquitousness is achieved.
        
        Args:
            belief_formula: The belief formula containing history variables
            valid_h: Constraint on history variables
            h_vars: List of history variables
            old_templates: Dictionary of templates indexed by generalization level
            memory_vars: List of memory variables
            latent_vars: List of latent variables
            max_iterations: Maximum number of iterations to prevent infinite loops
            
        Returns:
            Tuple of (templates_dict, updated_memory_vars, belief_count)
        """
        iteration = 0
        belief_count = 0  # Track number of counterexample beliefs found
        # templates is now a dict: {generalization_level: [list of templates]}
        templates = {k: v.copy() for k, v in old_templates.items()}
        
        # Initialize level 0 if not present
        if 0 not in templates:
            templates[0] = []

        generalization_level = 0

        while iteration < max_iterations:
            # Count total templates across all levels
            total_templates = sum(len(t_list) for t_list in templates.values())
            print(f"Mining iteration {iteration}, total templates: {total_templates}")
            print(f"Templates by level: {[(level, len(t_list)) for level, t_list in templates.items()]}")
            
            # Create disjunction of all current templates across all levels
            template_disjunction = BoolVal(False)
            all_templates_flat = []
            
            for level in sorted(templates.keys()):
                all_templates_flat.extend(templates[level])
            
            if len(all_templates_flat) > 0:
                memory = memory_vars[0]
                template_disjunction = Implies(memory == 0, all_templates_flat[0])
                for i in range(1, len(all_templates_flat)):
                    template_disjunction = And(template_disjunction, Implies(memory == i, all_templates_flat[i]))
        
        # Check if current templates satisfy ubiquitousness
            is_ubiquitous, model = self.check_template_ubiquitousness(
                belief_formula, valid_h, template_disjunction, memory_vars, latent_vars
            )
            
            if not is_ubiquitous:
                belief_count += 1  # Increment count when counterexample found
            
            if is_ubiquitous:
                print(f"Ubiquitousness achieved with {total_templates} templates")
                
                # Eliminate redundant templates from lower levels
                highest_level = max(templates.keys())
                
                if highest_level > 0 and len(templates[highest_level]) > 0:
                    print(f"\nEliminating redundant templates...")
                    
                    for level in range(0, highest_level):
                        if level not in templates or len(templates[level]) == 0:
                            continue
                        
                        templates_to_keep = []
                        
                        for template in templates[level]:
                            is_redundant = False
                            
                            for high_template in templates[highest_level]:
                                # Check if high_template subsumes template
                                is_subsumed, _ = self.check_template_ubiquitousness(
                                    template,           # belief_formula: the template we're checking
                                    BoolVal(True),      # valid_h: no constraint
                                    high_template,      # template: the higher-level template
                                    memory_vars,        # memory_vars
                                    latent_vars         # latent_vars
                                )
                                
                                if is_subsumed:
                                    is_redundant = True
                                    print(f"  Eliminated: level {level} template subsumed by level {highest_level} template")
                                    print(f"    Lower: {template}")
                                    print(f"    Higher: {high_template}")
                                    break
                            
                            if not is_redundant:
                                templates_to_keep.append(template)
                        
                        removed_count = len(templates[level]) - len(templates_to_keep)
                        templates[level] = templates_to_keep
                        
                        if removed_count > 0:
                            print(f"  Level {level}: removed {removed_count}, kept {len(templates_to_keep)}")
                
                # Clean up empty levels
                templates = {k: v for k, v in templates.items() if len(v) > 0}
                
                print(f"\nFinal template counts:")
                total_final = 0
                for level in sorted(templates.keys()):
                    print(f"  Level {level}: {len(templates[level])} templates")
                    total_final += len(templates[level])
                print(f"  Total: {total_final} templates")
            
                return (templates, memory_vars, belief_count)
            
            # Get counterexample and mine a new template (always at level 0)
            print(f"Counterexample found, mining new template...")
            new_template = self.mine_template(model, h_vars, belief_formula)
            new_template = normalize_formula(new_template)
            # Add the new template to level 0
            templates[0].append(new_template)
            print(f"Added template to level 0: {new_template}")
            print(f"Level 0 now has {len(templates[0])} templates")
            
            # Check if we should generalize (when level 0 has >= generalization_threshold templates)
            if len(templates[0]) >= self.generalization_threshold:
                print(f"\nLevel 0 has {len(templates[0])} templates, attempting generalization...")
                
                # Generalize from level 0 to level 1
                generalization_level = generalization_level + 1
                
                good_templates, bad_templates, generalized_memory = self.generalize_templates(
                    templates[0], memory_vars, generalization_level, latent_vars
                )
                memory_vars = generalized_memory

                # Initialize level if not present
                if generalization_level not in templates:
                    templates[generalization_level] = []
                
                # Add good generalized templates to the level
                templates[generalization_level].extend(good_templates)
                
                # Replace level 0 with bad templates (those that couldn't be generalized)
                templates[0] = bad_templates
                
                # Give this generalization level a second chance
                if len(bad_templates) <= self.min_bad_templates:
                    generalization_level = generalization_level - 1

                print(f"Generalization complete:")
                print(f"  Level 0 (concrete): {len(templates[0])} templates")
                print(f"  Level {generalization_level} ({generalization_level} holes): {len(templates[generalization_level])} templates")
                print(f"  Memory variables: {len(memory_vars)}")

            iteration += 1
        
        print(f"Warning: Reached max iterations ({max_iterations})")
        return (templates, memory_vars, belief_count)


    def vars_from_abs_obs(self, attribute, index):
        var_dict = []
        if attribute == 'obs':
            var_dict = self.game.make_observable_states(index)
        elif attribute == 'action':
            var_dict = self.game.make_actions(index)
        else:
            raise Exception("Unknown attribute type")
        return list(var_dict.values())


    def mine_all(self, beliefs):
        """
        Mine templates for all beliefs in the list.
        
        Args:
            beliefs: List of Belief objects
            
        Returns:
            Tuple of (templates_dict, updated_memory_vars)
        """
        all_templates = {}  # {generalization_level: [templates]}
        memory_vars = [Int('m0')]  # Initialize memory variables
        total_belief_count = 0  # Track total number of beliefs found across all mining
        
        for i, belief in enumerate(beliefs):
            print(f"\n{'='*60}")
            print(f"Mining templates for belief {i}")
            print(f"{'='*60}")
            
            # Get belief formula
            belief_formula = belief.get_formula()

            # Get state variables (latent variables)
            latent_vars = list(self.game.make_latent_states('org').values())
            
            h_vars = list(self.game.make_observable_states("org").values())
            valid_h = belief.get_feasible_obs()

            # Get observable indices from belief
            h_indices = belief.get_abs_obs()

            if h_indices != -1: 
                _, cur_index = h_indices[-1]
                cur_vars= list(self.game.make_observable_states(cur_index).values())
                obs_org_vars = list(self.game.make_observable_states("org").values())
                # Valid history constraint (initially allow all)
                # This could be refined based on game-specific constraints
                valid_h = belief.get_feasible_obs()
                for j in range(0, len(cur_vars)):
                    valid_h = And(valid_h, cur_vars[j] == obs_org_vars[j])

        
                # Construct history variables based on observation indices
                h_vars = []
                for attribute, index in h_indices:  
                    h_vars.extend(self.vars_from_abs_obs(attribute, index))
                h_vars.extend(obs_org_vars)

            # Mine templates for this belief with updated memory_vars
            templates, memory_vars, belief_count = self.mine_templates(
                #all_templates,  # Pass accumulated templates
                {},
                belief_formula=belief_formula,
                valid_h=valid_h,
                h_vars=h_vars,
                memory_vars=memory_vars,  # Pass current memory_vars
                latent_vars=latent_vars,
                max_iterations=100
            )
            
            total_belief_count += belief_count
            
            # Merge templates from this belief into all_templates
            for level, template_list in templates.items():
                if level not in all_templates:
                    all_templates[level] = []
                all_templates[level].extend(template_list)
            
            total_count = sum(len(t_list) for t_list in all_templates.values())
            print(f"Mined templates for belief {i}: {[(level, len(t_list)) for level, t_list in templates.items()]}")
            print(f"Updated memory_vars: {memory_vars}")
        
        print(f"\n{'='*60}")
        print(f"Total beliefs processed: {len(beliefs)}")
        total_templates = sum(len(t_list) for t_list in all_templates.values())
        print(f"Total templates: {total_templates}")
        print(f"Templates by level: {[(level, len(t_list)) for level, t_list in all_templates.items()]}")
        print(f"Final memory variables: {memory_vars}")
        print(f"Number of counterexample beliefs found: {total_belief_count}")
        print(f"{'='*60}\n")
        
        if self.aggressive_point_memory:
            from solver.point_templates import generalize_points, infer_finite_domains
            all_templates, memory_vars = generalize_points(
                all_templates, memory_vars, list(self.game.make_latent_states('org').values()),
                infer_finite_domains(self.game))
            print('Aggressive point-memory templates:', all_templates, flush=True)
        return (all_templates, memory_vars)


    def generalize_templates(self, templates, old_memory_vars, memory_size, latent_variables):
        """
        Generalize templates by replacing constants with memory variables.
        Always works on level 0 templates (concrete templates with no holes).
        Iteratively pick one template, add holes, check ubiquitousness against remaining templates.
        Keep good generalizations and remove subsumed templates.
        
        Args:
            templates: List of level 0 template formulas (no holes)
            old_memory_vars: Current list of memory variables
            memory_size: Target number of holes (generalization level)
            latent_variables: List of latent variables
            
        Returns:
            Tuple of (good_templates, bad_templates, updated_memory_vars)
        """
        remaining_templates = templates.copy()
        good_templates = []  # Templates that passed ubiquitousness check
        bad_templates = []   # Templates that failed ubiquitousness check

        # Each hole keeps the numeral's sort. In mixed Int/Real games, a
        # Real hole inside ToReal(Int-expression) makes reconstruction ill-sorted.
        # Reuse a separate variable for each slot and sort across templates.
        memory_vars = old_memory_vars.copy()

        def hole_memory(slot, constant):
            sort = constant.sort()
            variable = Const(f'm{slot + 1}_{sort}', sort)
            if not any(variable.eq(old) for old in memory_vars):
                memory_vars.append(variable)
            return variable

        round_num = 0
        
        while len(remaining_templates) > 0:
            print(f"\n{'='*60}")
            print(f"Generalization round {round_num}")
            print(f"Remaining level 0 templates: {len(remaining_templates)}")
            print(f"Good generalized templates so far: {len(good_templates)}")
            print(f"{'='*60}")
            
            # Pick one template arbitrarily (first one)
            template = remaining_templates[0]
            remaining_templates.pop(0)
            
            print(f"\nPicked template: {template}")
            
            # Extract all constants with their paths
            constant_holes = self.extract_constants_with_paths(template)
            print(f"Found {len(constant_holes)} constant holes")
            
            if len(constant_holes) == 0:
                # No constants to generalize, just add to bad templates
                bad_templates.append(template)
                print(f"No holes found, added to bad templates")
                round_num += 1
                continue
            
            # Limit holes to generalize based on memory_size
            holes_to_generalize = constant_holes
            
            # Generate all possible combinations of memory variable assignments
            from itertools import combinations, chain
            from math import comb

            # For each hole, choose exactly memory_size holes to replace
            num_holes = len(holes_to_generalize)

            # Generate all combinations of choosing memory_size holes from num_holes
            if num_holes == 0: 
                assert False
                print(f"Warning: no holes available, adding template to bad templates")
                bad_templates.append(template)
                round_num += 1
                continue
            elif num_holes < memory_size:
                # Not enough holes - replace all available holes
                print(f"Only {num_holes} holes available (less than {memory_size}), replacing all")
                
                # Build path-based substitutions for all holes
                path_substitutions = []
                for mem_idx, (path, constant_val) in enumerate(holes_to_generalize):
                    path_substitutions.append((path, constant_val, hole_memory(mem_idx, constant_val)))
                
                # Apply substitutions to create generalized template
                generalized = self.substitute_constants_by_path(template, path_substitutions)
                print(f"  Generalized (all {num_holes} holes): {generalized}")
                
                # Add directly to good templates
                good_templates.append(generalized)
                print(f"  ✓ Added to good templates (replaced all available holes)")
                
                round_num += 1
                continue
            else:
                assert(num_holes >= memory_size)
                memory_size_actual = memory_size

            if self.options.prioritize_seed_differences:
                # Generate all ways to choose memory_size_actual positions from num_holes positions
                # Try holes that differ between structurally matching seeds first.
                # This also tries smaller matching differences before the full
                # combinations; each proposal is checked before acceptance.
                hole_indices = {path: i for i, (path, _) in enumerate(holes_to_generalize)}
                preferred = []
                for other in remaining_templates:
                    paths = self.differing_constant_paths(template, other)
                    if paths and len(paths) <= memory_size_actual and all(p in hole_indices for p in paths):
                        choice = tuple(sorted(hole_indices[p] for p in paths))
                        if choice not in preferred:
                            preferred.append(choice)
                replacement_choices = chain(preferred, combinations(range(num_holes), memory_size_actual))
                print(f"Generated {comb(num_holes, memory_size_actual)} replacement choices; {len(preferred)} prioritized")

            else:
                replacement_choices = list(combinations(range(num_holes), memory_size_actual))
                print(f"Generated {len(replacement_choices)} replacement choices")

            found_good_generalization = False
            for choice_indices in replacement_choices:
                # choice_indices is a tuple of indices to replace, e.g., (0,) means replace hole 0
                
                # Build path-based substitutions
                path_substitutions = []
                
                for mem_idx, hole_idx in enumerate(choice_indices):
                    path, constant_val = holes_to_generalize[hole_idx]
                    path_substitutions.append((path, constant_val, hole_memory(mem_idx, constant_val)))
                
                # Apply path-based substitutions to create generalized template
                generalized = self.substitute_constants_by_path(template, path_substitutions)
                
                print(f"\n  Testing generalization with holes at {[p for p, _, _ in path_substitutions]}")
                print(f"  Generalized: {generalized}")
                
                # Check if this generalization subsumes any remaining templates
                templates_to_remove = []
                exist_pass = False
                
                for other_template in remaining_templates:
                    # Check if generalized template is ubiquitous for other_template
                    is_ubiquitous, model = self.check_template_ubiquitousness(
                        other_template,
                        BoolVal(True),
                        generalized,
                        memory_vars,
                        latent_variables
                    )
                    
                    if is_ubiquitous:
                        print(f"    ✓ Subsumes: {other_template}")
                        templates_to_remove.append(other_template)
                        exist_pass = True
                
                # If this generalization subsumed at least one template
                if exist_pass:
                    print(f"\n  ✓ Good generalization found!")
                    good_templates.append(generalized)
                    
                    # Remove all subsumed templates
                    for template_to_remove in templates_to_remove:
                        remaining_templates.remove(template_to_remove)
                        print(f"  Removed subsumed template: {template_to_remove}")
                    
                    found_good_generalization = True
                    break  # Move to next round with a new template
            
            # If no good generalization found, add original template to bad templates
            if not found_good_generalization:
                print(f"\n  No good generalization found, keeping original template at level 0")
                bad_templates.append(template)
            
            round_num += 1
        
        print(f"\n{'='*60}")
        print(f"Generalization complete!")
        print(f"Original level 0 templates: {len(templates)}")
        print(f"Good generalized templates (level {memory_size}): {len(good_templates)}")
        print(f"Bad templates (staying at level 0): {len(bad_templates)}")
        print(f"{'='*60}\n")
        
        return (good_templates, bad_templates, memory_vars)

    def differing_constant_paths(self, formula, other):
        """Find numeric differences in matching trees, allowing And/Or reordering.

        Return None when any nonnumeric structure differs. Coefficients and
        divisors remain fixed, as in extract_constants_with_paths.
        """
        def shape(expr):
            if is_int_value(expr) or is_rational_value(expr):
                return ('number', str(expr.sort()))
            if is_mul(expr) or is_div(expr) or expr.num_args() == 0:
                return ('fixed', expr.sexpr())
            children = [shape(c) for c in expr.children()]
            if is_and(expr) or is_or(expr):
                children.sort(key=repr)
            return (str(expr.decl()), tuple(children))

        def compare(left, right, path):
            if left.eq(right):
                return []
            if shape(left) != shape(right):
                return None
            if is_int_value(left) or is_rational_value(left):
                return [path]
            left_children = list(enumerate(left.children()))
            right_children = list(right.children())
            if is_and(left) or is_or(left):
                left_children.sort(key=lambda item: (repr(shape(item[1])), item[1].sexpr()))
                right_children.sort(key=lambda child: (repr(shape(child)), child.sexpr()))
            paths = []
            for (index, child), partner in zip(left_children, right_children):
                differences = compare(child, partner, path + (index,))
                if differences is None:
                    return None
                paths.extend(differences)
            return paths

        return compare(formula, other, ())

    def is_fixed_domain(self, formula):
        """Return whether a finite-domain predicate should retain its numeric literals."""
        if self.game is None or not is_bool(formula):
            return False
        if self._finite_domains is None:
            from solver.point_templates import infer_finite_domains
            self._finite_domains = infer_finite_domains(self.game)
        key = formula.sexpr()
        if key in self._fixed_domain_cache:
            return self._fixed_domain_cache[key]
        from z3.z3util import get_vars
        variables = get_vars(formula)
        fixed = bool(variables) and all(
            str(variable) in self._finite_domains
            and len(self._finite_domains[str(variable)]) == 2
            for variable in variables
        )
        if is_eq(formula) and len(variables) == 1 and str(variables[0]) in self._finite_domains:
            # Equality selects a discrete mode (including a timer or an abstract
            # numeric band). Bounds over the same variable may still be learned.
            fixed = True
        if not fixed and len(variables) == 1 and str(variables[0]) in self._finite_domains:
            variable = variables[0]
            domain = Or(*[variable == v for v in self._finite_domains[str(variable)]])
            solver = Solver()
            solver.set(timeout=1000)
            solver.add(Xor(formula, domain))
            fixed = solver.check() == unsat
        self._fixed_domain_cache[key] = fixed
        return fixed

    def extract_constants_with_paths(self, formula, path=[]):
        """
        Extract all numeric constants from a formula along with their paths.
        
        Args:
            formula: Z3 formula
            path: Current path (list of child indices)
            
        Returns:
            List of (path, constant) tuples where path uniquely identifies the constant's location
        """
        constant_holes = []
        if self.options.preserve_discrete_predicates and self.is_fixed_domain(formula):
            return constant_holes
        
        # Check if current expression is a constant
        if is_const(formula) and not is_var(formula):
            if is_int_value(formula) or is_rational_value(formula):
                constant_holes.append((tuple(path), formula))
        
        # Recursively visit children with updated paths
        if not is_mul(formula) and not is_div(formula):
            for i, child in enumerate(formula.children()):
                child_holes = self.extract_constants_with_paths(child, path + [i])
                constant_holes.extend(child_holes)
        
        return constant_holes

    def substitute_constants_by_path(self, formula, path_substitutions):
        """
        Substitute constants at specific paths with memory variables.
        
        Args:
            formula: Z3 formula
            path_substitutions: List of (path, old_constant, new_memory_var) tuples
            
        Returns:
            Formula with specified constants replaced
        """
        # Create a map from path to memory variable
        path_map = {}
        for path, old_const, mem_var in path_substitutions:
            path_map[path] = (old_const, mem_var)
    
        def replace_at_path(expr, current_path=[]):
            # Check if we should replace at this path
            path_tuple = tuple(current_path)
            if path_tuple in path_map:
                old_const, mem_var = path_map[path_tuple]
                # Verify the constant matches
                if is_const(expr) and expr.eq(old_const):
                    return mem_var
        
            # If composite expression, recursively process children
            if expr.num_args() > 0:
                new_children = []
                for i, child in enumerate(expr.children()):
                    new_child = replace_at_path(child, current_path + [i])
                    new_children.append(new_child)
            
                # Reconstruct expression with new children
                decl = expr.decl()
                if expr.num_args() == len(new_children):
                    return decl(*new_children)
                else:
                    # Fallback to manual reconstruction for special cases
                    if is_and(expr):
                        return And(*new_children)
                    elif is_or(expr):
                        return Or(*new_children)
                    elif is_not(expr):
                        return Not(new_children[0])
                    elif is_eq(expr):
                        return new_children[0] == new_children[1]
                    elif is_distinct(expr):
                        return Distinct(*new_children)
                    elif is_lt(expr):
                        return new_children[0] < new_children[1]
                    elif is_le(expr):
                        return new_children[0] <= new_children[1]
                    elif is_gt(expr):
                        return new_children[0] > new_children[1]
                    elif is_ge(expr):
                        return new_children[0] >= new_children[1]
                    elif is_add(expr):
                        return Sum(*new_children)
                    elif is_sub(expr):
                        return new_children[0] - new_children[1]
                    elif is_mul(expr):
                        return Product(*new_children)
                    elif is_div(expr):
                        return new_children[0] / new_children[1]
                    elif is_implies(expr):
                        return Implies(new_children[0], new_children[1])
                    else:
                        return expr
        
            return expr
    
        result = replace_at_path(formula)
        return result
