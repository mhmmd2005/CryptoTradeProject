(function ($) {
	"use strict";


/*===========================================
	=            Windows Load          =
=============================================*/
$(window).on('load', function () {
    preloader();
    wowAnimation();
});


/*===========================================
	=            Preloader          =
=============================================*/
function preloader() {
	$('#preloader').delay(0).fadeOut();
}


/*===========================================
	=    		Mobile Menu			      =
=============================================*/
//SubMenu Dropdown Toggle
if ($('.tgmenu__wrap li.menu-item-has-children ul').length) {
	$('.tgmenu__wrap .navigation li.menu-item-has-children').append('<div class="dropdown-btn"><span class="plus-line"></span></div>');
}

//Mobile Nav Hide Show
if ($('.tgmobile__menu').length) {

	var mobileMenuContent = $('.tgmenu__wrap .tgmenu__main-menu').html();
	$('.tgmobile__menu .tgmobile__menu-box .tgmobile__menu-outer').append(mobileMenuContent);

	//Dropdown Button
	$('.tgmobile__menu li.menu-item-has-children .dropdown-btn').on('click', function () {
		$(this).toggleClass('open');
		$(this).prev('ul').slideToggle(300);
	});
	//Menu Toggle Btn
	$('.mobile-nav-toggler').on('click', function () {
		$('body').addClass('mobile-menu-visible');
	});

	//Menu Toggle Btn
	$('.tgmobile__menu-backdrop, .tgmobile__menu .close-btn').on('click', function () {
		$('body').removeClass('mobile-menu-visible');
	});
}


/*===========================================
	=     Menu sticky & Scroll to top      =
=============================================*/
$(window).on('scroll', function () {
	var scroll = $(window).scrollTop();
	if (scroll < 245) {
		$("#sticky-header").removeClass("sticky-menu");
		$('.scroll-to-target').removeClass('open');
        $("#header-fixed-height").removeClass("active-height");

	} else {
		$("#sticky-header").addClass("sticky-menu");
		$('.scroll-to-target').addClass('open');
        $("#header-fixed-height").addClass("active-height");
	}
});


/*===========================================
	=           Scroll Up  	         =
=============================================*/
if ($('.scroll-to-target').length) {
  $(".scroll-to-target").on('click', function () {
    var target = $(this).attr('data-target');
    // animate
    $('html, body').animate({
      scrollTop: $(target).offset().top
    }, 0);

  });
}


/*===========================================
	=          Data Background    =
=============================================*/
$("[data-background]").each(function () {
	$(this).css("background-image", "url(" + $(this).attr("data-background") + ")")
});

$("[data-bg-color]").each(function () {
	$(this).css("background-color", $(this).attr("data-bg-color"));
});



/*=============================================
	=          One page Menu               =
=============================================*/
var scrollLink = $('.section-link');
// Active link switching
$(window).on('scroll', function () {
	var scrollbarLocation = $(this).scrollTop();

	scrollLink.each(function () {

		var sectionOffset = $(this.hash).offset().top - 90;

		if (sectionOffset <= scrollbarLocation) {
			$(this).parent().addClass('active');
			$(this).parent().siblings().removeClass('active');
		}
	});
});
//jQuery for page scrolling feature - requires jQuery Easing plugin
$(function () {
	$('a.section-link[href*="#"]:not([href="#"])').on('click', function () {
		if (location.pathname.replace(/^\//, '') == this.pathname.replace(/^\//, '') && location.hostname == this.hostname) {
			var target = $(this.hash);
			target = target.length ? target : $('[name=' + this.hash.slice(1) + ']');
			if (target.length) {
				$('html, body').animate({
					scrollTop: (target.offset().top - 85)
				}, 1200, "easeInOutExpo");
				return false;
			}
		}
	});
});


/*=============================================
	=        Brand Active		      =
=============================================*/
var brandSwiper = new Swiper('.brand-active', {
    // Optional parameters
    slidesPerView: 6,
    spaceBetween: 24,
    loop: true,
    breakpoints: {
        '1500': {
            slidesPerView: 6,
        },
        '1200': {
            slidesPerView: 5,
        },
        '992': {
            slidesPerView: 4,
        },
        '768': {
            slidesPerView: 3,
        },
        '576': {
            slidesPerView: 3,
        },
        '0': {
            slidesPerView: 2,
        },
    },
});



/*=============================================
	=        Ticker Active	      =
=============================================*/
var swiper = new Swiper(".ticker-active", {
    loop: true,
    freemode: true,
    slidesPerView: 'auto',
    spaceBetween: 60,
    centeredSlides: true,
    allowTouchMove: false,
    speed: 5000,
    autoplay: {
        delay: 1,
        disableOnInteraction: true,
    },
    breakpoints: {
        '1500': {
            spaceBetween: 60,
        },
        '1200': {
            spaceBetween: 60,
        },
        '992': {
            spaceBetween: 40,
        },
        '768': {
            spaceBetween: 30,
        },
        '576': {
            spaceBetween: 20,
        },
        '0': {
            spaceBetween: 20,
        },
    },
});


/*=============================================
	=    	  Countdown Active  	         =
=============================================*/
$('[data-countdown]').each(function () {
	var $this = $(this), finalDate = $(this).data('countdown');
	$this.countdown(finalDate, function (event) {
		$this.html(event.strftime('<div class="time-count day"><span>%D</span>Days</div><div class="time-count hour"><span>%H</span>hour</div><div class="time-count min"><span>%M</span>minute</div><div class="time-count sec"><span>%S</span>second</div>'));
	});
});



/*===========================================
	=         Marquee Active         =
=============================================*/
if ($(".marquee_mode").length) {
    $('.marquee_mode').marquee({
        speed: 20,
        gap: 20,
        delayBeforeStart: 0,
        direction: 'left',
        duplicated: true,
        startVisible:true,
    });
}




/*===========================================
      =       Odometer Active    =
=============================================*/
$('.odometer').appear(function (e) {
	var odo = $(".odometer");
	odo.each(function () {
		var countNumber = $(this).attr("data-count");
		$(this).html(countNumber);
	});
});


/*===========================================
	=        Wow Active      =
=============================================*/
function wowAnimation() {
	var wow = new WOW({
		boxClass: 'wow',
		animateClass: 'animated',
		offset: 0,
		mobile: false,
		live: true
	});
	wow.init();
}


})(jQuery);