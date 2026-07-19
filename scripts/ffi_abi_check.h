// scripts/ffi_abi_check.h — ABI-class comparison between Zen's foreign prototypes and the REAL
// system-header prototypes. Used only by scripts/ffi_verify.sh (never linked into anything).
//
// Why not just redeclare Zen's prototypes under the headers and let C's conflicting-types rule
// fire?  Because Zen's lowering makes two DELIBERATE, ABI-identical modeling choices that C calls
// "conflicting types":
//   - Zen has no size_t/ssize_t: sizes are i64 (long) where glibc says unsigned long. Same
//     register, same width — but incompatible C types.
//   - RawPtr<u8> lowers to uint8_t* where glibc says void* / struct stat* / FILE* …. All object
//     pointers are one register class on every supported ABI — but incompatible C types.
// A verbatim-redeclare gate would therefore be ~100% false positives. This header instead
// decomposes the header's REAL function type (via decltype on the included prototype) with
// templates and compares it slot-by-slot against Zen's belief at the level that corrupts memory:
//
//   caught  — wrong arg count; integer/pointer/float register-class confusion; wrong integer or
//             float WIDTH; function-pointer vs object-pointer confusion (recursing into the
//             pointed-to signature); void vs value return; Zen inventing parameters a
//             non-variadic C function does not have; Zen declaring a param const-pointee where
//             the header says the callee WRITES through it (callers would pass read-only
//             memory), and Zen declaring a non-const return where the header says const.
//   allowed — integer signedness at equal width (i64 vs size_t: bit-identical in registers, a
//             documented Zen modeling freedom); differing object-pointee types (uint8_t* vs
//             void*/struct*: one register class); extra Zen args riding a variadic header's
//             `...` (e.g. open's mode); glibc's noexcept/__restrict decoration.
//
// C++17, glibc/Linux. Compile with: g++ -std=gnu++17 -fsyntax-only -Werror.
#pragma once
#include <cstddef>
#include <type_traits>

namespace zen_ffi_check {

template <class... T> struct plist {};

// Decompose a function type into (return, params, variadic?), stripping noexcept (glibc's
// __THROW is noexcept in C++, and noexcept is part of the type since C++17).
template <class F> struct fsig; // primary undefined: non-function decltype = hard error
template <class R, class... A> struct fsig<R(A...)> {
    using ret = R;
    using args = plist<A...>;
    static constexpr bool variadic = false;
};
template <class R, class... A> struct fsig<R(A..., ...)> {
    using ret = R;
    using args = plist<A...>;
    static constexpr bool variadic = true;
};
template <class R, class... A> struct fsig<R(A...) noexcept> : fsig<R(A...)> {};
template <class R, class... A> struct fsig<R(A..., ...) noexcept> : fsig<R(A..., ...)> {};

template <class Z, class H> struct sig_same;

// One value slot: Z = Zen's belief, H = the header's truth. IsRet flips the const-direction
// rule (param: Zen-const over a writing callee is the unsound direction; return: Zen dropping
// the header's const is).
template <class Z, class H, bool IsRet> constexpr bool val_ok() {
    using ZB = std::remove_cv_t<Z>;
    using HB = std::remove_cv_t<H>;
    if constexpr (std::is_pointer_v<ZB> && std::is_pointer_v<HB>) {
        using ZE = std::remove_pointer_t<ZB>;
        using HE = std::remove_pointer_t<HB>;
        if constexpr (std::is_function_v<ZE> || std::is_function_v<HE>) {
            if constexpr (std::is_function_v<ZE> && std::is_function_v<HE>)
                return sig_same<ZE, HE>::value; // recurse: callback signatures must agree too
            else
                return false; // function pointer confused with object pointer
        } else {
            constexpr bool zc = std::is_const_v<ZE>;
            constexpr bool hc = std::is_const_v<HE>;
            return IsRet ? !(hc && !zc) : !(zc && !hc);
        }
    } else if constexpr ((std::is_integral_v<ZB> || std::is_enum_v<ZB>) &&
                         (std::is_integral_v<HB> || std::is_enum_v<HB>)) {
        return sizeof(ZB) == sizeof(HB); // width only; signedness is a documented freedom
    } else if constexpr (std::is_floating_point_v<ZB> && std::is_floating_point_v<HB>) {
        return sizeof(ZB) == sizeof(HB); // float vs double differ in ABI
    } else {
        return false; // register-class mismatch (int vs pointer vs float) — hard drift
    }
}

template <class Z, class H> constexpr bool ret_ok() {
    if constexpr (std::is_void_v<Z> || std::is_void_v<H>)
        return std::is_void_v<Z> && std::is_void_v<H>;
    else
        return val_ok<Z, H, true>();
}

// Pairwise parameter walk. HVariadic: the header ends in `...` — extra Zen params ride it
// (fixed-position integer/pointer args pass identically on the supported ABIs).
template <class ZL, class HL, bool HVariadic> struct params_ok;
template <bool V> struct params_ok<plist<>, plist<>, V> : std::true_type {};
template <class Z0, class... Zs>
struct params_ok<plist<Z0, Zs...>, plist<>, true> : std::true_type {};
template <class Z0, class... Zs>
struct params_ok<plist<Z0, Zs...>, plist<>, false> : std::false_type {}; // Zen invented params
template <class H0, class... Hs, bool V>
struct params_ok<plist<>, plist<H0, Hs...>, V> : std::false_type {}; // Zen dropped params
template <class Z0, class... Zs, class H0, class... Hs, bool V>
struct params_ok<plist<Z0, Zs...>, plist<H0, Hs...>, V>
    : std::bool_constant<val_ok<Z0, H0, false>() &&
                         params_ok<plist<Zs...>, plist<Hs...>, V>::value> {};

template <class Z, class H>
struct sig_same
    : std::bool_constant<!fsig<Z>::variadic &&
                         ret_ok<typename fsig<Z>::ret, typename fsig<H>::ret>() &&
                         params_ok<typename fsig<Z>::args, typename fsig<H>::args,
                                   fsig<H>::variadic>::value> {};

// Left undefined on mismatch so the compiler error PRINTS both full signatures
// (drift<zen-type, header-type, false> is an incomplete type).
template <class Z, class H, bool OK = sig_same<Z, H>::value> struct drift;
template <class Z, class H> struct drift<Z, H, true> : std::true_type {};

} // namespace zen_ffi_check

// zen_ffi:: holds the prototypes exactly as `zenc emit` lowered them (pasted by the script);
// `::sym` is the system header's declaration of the same symbol.
#define ZEN_FFI_CHECK(sym)                                                                       \
    static_assert(zen_ffi_check::drift<decltype(zen_ffi::sym), decltype(::sym)>::value,          \
                  "FFI drift: `" #sym "` — Zen foreign decl disagrees with the system header");
