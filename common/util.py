from z3 import *

#set_option("smt.arith.nl", False) 
#set_option("smt.arith.solver", 2)
#def flatten(l) -> list:
#    ret = []
#    if(isinstance(l, list) or isinstance(l, np.ndarray)):
#        for item in l:
#            ret.extend(flatten(item))
#        return ret
#    else:
#        return [l]

def normalize_formula(node: z3.BoolRef):
    """
    Normalize an LRA/LIA formula by ensuring each atomic constraint has:
    - Left side: only variables (sum of variables)
    - Right side: only constants (single constant value)
    
    Examples:
        x + 5 <= 10 + y  →  x - y <= 5
        2*x - 3 >= y + 7  →  2*x - y >= 10
        x == 5  →  x == 5 (already normalized)
    
    Args:
        node: Z3 Boolean formula (potentially with And/Or/Not structure)
        
    Returns:
        Normalized formula with same logical structure
    """
    
    def extract_var_part(expr):
        """
        Extract the variable part by traversing only + and - operations.
        Treat any mul/div containing variables as a variable term.
        """
        #print(expr)
        # Base case: check if entire expression is a constant        
        if is_const(expr):
            if is_int_value(expr) or is_rational_value(expr):
                return (expr, False)
            else:
                return (expr, True)

        # If it's multiplication or division with variables, treat the whole thing as variable
        if is_mul(expr) or is_div(expr):
            children = expr.children()
            is_variable = False
            for child in children:
                _, sub_is_variable = extract_var_part(child)
                if sub_is_variable:
                    is_variable = True
                    break
            return (expr, is_variable)
        
        # Recursive case: addition
        if is_add(expr):
            children = expr.children()
            #assert len(children) == 2
            var_children = []
            for child in children:
                var_part, sub_is_variable = extract_var_part(child)
                if sub_is_variable:
                    var_children.append(var_part)

            # Should never happen for the root node
            if len(var_children) == 0:
                return (BoolVal(False), False)
            elif len(var_children) == 1:
                return (var_children[0], True)
            else:
                return (Sum(*var_children), True)
        
        # Recursive case: subtraction
        elif is_sub(expr):
            children = expr.children()
            assert len(children) == 2
            left_var, is_variable_left = extract_var_part(children[0])
            right_var, is_variable_right = extract_var_part(children[1])

            if is_variable_left == False and is_variable_right == False:
                return (BoolVal(False), False)
            elif is_variable_left == True and is_variable_right == False:
                return (left_var, True)
            elif is_variable_left == False and is_variable_right == True:
                return (-right_var, True)
            else:
                return (left_var - right_var, True)
        
        # Shouldn't reach here
        assert False
        #return expr
    
    def extract_const_part(expr):
        """Return the constant arithmetic part, replacing symbolic leaves with zero."""
        
        # Base case: constant
        if is_const(expr):
            if is_int_value(expr) or is_rational_value(expr):
                return expr
            else:
                return IntVal(0) if is_int(expr) else RealVal(0)

        # If it's multiplication or division
        if is_mul(expr) or is_div(expr):
            children = expr.children()
            values = []
            for child in children:
                values.append(extract_const_part(child))

            assert len(values) == 2
            if is_mul(expr):
                return values[0] * values[1]
            else:
                assert False
        
        # Recursive case: addition
        if is_add(expr):
            children = expr.children()
            values = []
            for child in children:
                values.append(extract_const_part(child))
            
            return Sum(*values)
        
        # Recursive case: subtraction
        elif is_sub(expr):
            children = expr.children()
            assert len(children) == 2
            left_const = extract_const_part(children[0])
            right_const = extract_const_part(children[1])
            return left_const - right_const
        
        # Shouldn't reach here
        assert False
    
    def normalize_atomic(expr):
        """Normalize an arithmetic comparison (<=, <, >=, >, or ==)."""
        if not (is_le(expr) or is_lt(expr) or is_ge(expr) or is_gt(expr) or is_eq(expr)):
            # Not a comparison, return as-is (could be a boolean variable)
            return expr
        
        # Get the children (left and right sides of comparison)
        children = expr.children()
        if len(children) != 2:
            return expr
        
        left = children[0]
        right = children[1]
        # Boolean equivalence is not an arithmetic equality.
        if is_bool(left) or is_bool(right):
            return expr

        # Move everything to left side: left - right
        combined = simplify(left - right)
        
        # Extract variables and constants
        var_part, has_var = extract_var_part(combined)
        if not has_var:
            return simplify(expr)
        const_part = extract_const_part(combined)
        # Simplify both parts
        var_part = simplify(var_part)
        const_part = simplify(const_part)
        
        # Negate the constant to move it to right side: var_part <op> -const_part
        negated_const = simplify(-const_part)
        
        # Reconstruct the comparison WITHOUT calling simplify on the result
        # This preserves the order: var_part <op> negated_const
        if is_le(expr):
            return var_part <= negated_const
        elif is_lt(expr):
            return var_part < negated_const
        elif is_ge(expr):
            return var_part >= negated_const
        elif is_gt(expr):
            return var_part > negated_const
        elif is_eq(expr):
            return var_part == negated_const
        else:
            return expr
    
    # Base case: atomic constraint
    if is_le(node) or is_lt(node) or is_ge(node) or is_gt(node) or is_eq(node):
        return normalize_atomic(node)
    
    # Boolean variable or constant
    if is_bool(node) and (is_const(node) or is_var(node)):
        return node
    
    if is_true(node) or is_false(node):
        return node
    
    # Recursive cases: preserve structure
    if is_and(node):
        children = node.children()
        normalized_children = [normalize_formula(child) for child in children]
        return And(*normalized_children)
    
    elif is_or(node):
        children = node.children()
        normalized_children = [normalize_formula(child) for child in children]
        return Or(*normalized_children)
    
    elif is_not(node):
        child = node.children()[0]
        
        # If negating a comparison, push negation inside
        if is_le(child):  # not (a <= b) → a > b
            ch = child.children()
            return normalize_formula(ch[0] > ch[1])
        elif is_lt(child):  # not (a < b) → a >= b
            ch = child.children()
            return normalize_formula(ch[0] >= ch[1])
        elif is_ge(child):  # not (a >= b) → a < b
            ch = child.children()
            return normalize_formula(ch[0] < ch[1])
        elif is_gt(child):  # not (a > b) → a <= b
            ch = child.children()
            return normalize_formula(ch[0] <= ch[1])
        elif is_eq(child):  # not (a == b) → keep as Not
            normalized_eq = normalize_formula(child)
            return Not(normalized_eq)
        else:
            # Recursively normalize the inner expression
            normalized_child = normalize_formula(child)
            return Not(normalized_child)
    
    elif is_implies(node):
        children = node.children()
        return Implies(normalize_formula(children[0]), normalize_formula(children[1]))
    
    else:
        # Unknown node type, return as-is
        return node

def recur_simplify(node: z3.BoolRef, alpha: z3.BoolRef):
    if z3.is_and(node) or z3.is_or(node): 
        children = node.children()
        new_children = []
        while True: 
            #print(children)
            for i in range(0, len(children)): 
                new_alpha = alpha
                for j in range(0, len(children)): 
                    if j < i: 
                        if z3.is_and(node): 
                            new_alpha = z3.And(new_alpha, new_children[j])
                        else: 
                            new_alpha = z3.And(new_alpha, z3.Not(new_children[j]))
                    if j > i: 
                        if z3.is_and(node):
                            new_alpha = z3.And(new_alpha, children[j])
                        else: 
                            new_alpha = z3.And(new_alpha, z3.Not(children[j]))                        
                new_children.append(recur_simplify(children[i], new_alpha))
            # Exit condition of the while loop
            if children == new_children: 
                break
            #Need to do the prune here for strictly decreasing number of leaves
            pruned = []
            if z3.is_and(node): 
                for child in new_children: 
                    if child == z3.BoolVal(False): 
                        pruned = [z3.BoolVal(False)]
                        break
                    elif child == z3.BoolVal(True):
                        continue
                    else: 
                        pruned.append(child)
                if pruned == []: 
                    pruned = [z3.BoolVal(True)]
            else: 
                for child in new_children: 
                    if child == z3.BoolVal(True): 
                        pruned = [z3.BoolVal(True)]
                        break
                    elif child == z3.BoolVal(False):
                        continue
                    else: 
                        pruned.append(child)
                if pruned == []: 
                    pruned = [z3.BoolVal(False)]
            children = pruned
            new_children = []

        if len(new_children) == 1: 
            return new_children[0]

        if z3.is_and(node): 
            return z3.And(new_children)
        else: 
            return z3.Or(new_children)
        
    else:
        s = z3.Solver()
        # alpha => N
        s.add(z3.And(alpha, z3.Not(node)))
        if s.check() == z3.unsat: 
            return z3.BoolVal(True)
        s = z3.Solver()
        # alpha => not N
        s.add(z3.And(alpha, node))
        if s.check() == z3.unsat: 
            return z3.BoolVal(False)
        return node

def quantifier_eliminate(formula):
	tactic = z3.Then(
		# 'fm',

		'qe2',
		# 'qe',
		'solve-eqs',
		'propagate-values2',
		'propagate-ineqs',

		# 'demodulator',
		# 'dom-simplify',

		'purify-arith',
		'simplify',
		'unit-subsume-simplify',

		'solver-subsumption',

		# 'aig',
		# 'sat-preprocess',
		# 'fm',
		# 'ctx-solver-simplify',
		# 'ctx-simplify,
		# 'add-bounds',
    )
	tactic_hard = z3.Then(
        'qe2',
		#'qe-light', 
		'simplify', 
        #'smt'
        #Repeat('ctx-solver-simplify')
	)
	g = Goal()
	g.add(formula)
	result = tactic_hard(g).as_expr()
	simplified_result = simplify(result, som=True)
	#return recur_simplify(result, BoolVal(True))
	return simplified_result


def to_cnf(self):
    """
    Convert the belief formula to CNF
    
    Returns:
        CNF formula
    """
    cnf_tactic = Tactic('tseitin-cnf')
    goal = Goal()
    goal.add(self.formula)
    result = cnf_tactic(goal)
    return result.as_expr()

def calculate_formula_size(formula):
    """Calculate the number of AST nodes in a Z3 formula"""
    if is_const(formula) and formula.decl().kind() == Z3_OP_UNINTERPRETED:
        return 1
    elif is_const(formula):
        return 1
    else:
        # Count this node plus all children
        size = 1
        for child in formula.children():
            size += calculate_formula_size(child)
        #print(size)
        return size